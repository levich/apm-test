"""X25519 ECHConfigList (RFC 9849), combined PEM (RFC 9934)."""

import base64
import secrets
import struct
import textwrap
import uuid

import dns.exception
import dns.resolver
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from apm.db import Resource
from apm.security import atomic_write
from apm.services import enqueue_apply


def key_pair(public_name, config_id=None):
    name = public_name.encode("idna")
    if not 1 <= len(name) <= 255 or name.startswith(b"*."):
        raise ValueError("ECH public name must be a concrete DNS name")
    private = X25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    config_id = secrets.randbelow(256) if config_id is None else config_id
    contents = struct.pack("!BHH", config_id, 0x0020, len(public)) + public
    contents += struct.pack("!HHHBB", 4, 1, 1, 0, len(name)) + name + b"\x00\x00"
    configuration = struct.pack("!HH", 0xFE0D, len(contents)) + contents
    encoded = base64.b64encode(struct.pack("!H", len(configuration)) + configuration).decode()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    pem += (
        "-----BEGIN ECHCONFIG-----\n" + "\n".join(textwrap.wrap(encoded, 64)) + "\n-----END ECHCONFIG-----\n"
    ).encode()
    return pem, encoded


def generate(database, config, resource_id):
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        if not resource or resource.kind != "ech":
            raise ValueError("ECH profile not found")
        data = resource.data
        if data.get("pending_key"):
            raise ValueError("Activate or remove the existing pending ECH key before rotating")
        # Avoid the active configuration identifier on rotation.
        pem, encoded = key_pair(data["public_name"])
        key_id = uuid.uuid4().hex
        atomic_write(config.data_dir / "ech" / resource_id / (key_id + ".pem"), pem, 0o640)
        resource.data = {**data, "pending_key": key_id, "config": encoded, "status": "awaiting_dns"}
        resource.version += 1
    return {"status": "awaiting_dns", "https_record": f'1 . ech="{encoded}"', "domains": data["domains"]}


def confirm(database, config, resource_id, resolver=None):
    resolver = resolver or dns.resolver.Resolver()
    with database.session() as session:
        resource = session.get(Resource, resource_id)
        if not resource or resource.kind != "ech" or not resource.data.get("pending_key"):
            raise ValueError("ECH key is not awaiting DNS publication")
        data = resource.data
        expected = base64.b64decode(data["config"], validate=True)
        for name in data["domains"]:
            try:
                answers = resolver.resolve(name, "HTTPS", lifetime=10)
            except dns.exception.DNSException:
                raise ValueError("ECH HTTPS record is not published for every domain") from None
            if not any(getattr(answer.params.get(5), "ech", None) == expected for answer in answers):
                raise ValueError("Published ECHConfigList does not match the pending key")
        resource.data = {
            **data,
            "status": "ready",
            "previous_key": data.get("current_key", ""),
            "current_key": data["pending_key"],
            "pending_key": "",
        }
        resource.version += 1
        return enqueue_apply(session)
