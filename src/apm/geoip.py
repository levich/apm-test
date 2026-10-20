import hashlib
import io
import tarfile

import httpx
from sqlalchemy import select

from apm.db import Resource, now, state_set
from apm.security import Vault, atomic_write
from apm.services import enqueue_apply


def update(database, config, resource_id, client=None):
    with database.session() as session:
        profile = session.get(Resource, resource_id)
        if not profile or profile.kind != "geo-policies":
            raise ValueError("GeoIP profile not found")
        credentials = Vault(config.data_dir).decrypt(profile.secret) if profile.secret else {}
    if not credentials.get("account_id") or not credentials.get("license_key"):
        raise ValueError("MaxMind account_id and license_key are required")
    files = {}
    client = client or httpx.Client(timeout=60, follow_redirects=True)
    for edition in ("GeoLite2-Country", "GeoLite2-ASN"):
        response = client.get(
            f"https://download.maxmind.com/geoip/databases/{edition}/download",
            params={"suffix": "tar.gz"},
            auth=(credentials["account_id"], credentials["license_key"]),
        )
        if response.is_error:
            raise ValueError("GeoIP download failed: HTTP " + str(response.status_code))
        if len(response.content) > 128 * 1024**2:
            raise ValueError("GeoIP archive exceeds the size limit")
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as bundle:
            entries = [
                entry for entry in bundle if entry.isfile() and entry.name.endswith("/" + edition + ".mmdb")
            ]
            if len(entries) != 1 or entries[0].size > 256 * 1024**2:
                raise ValueError("Unexpected GeoIP archive contents")
            data = bundle.extractfile(entries[0]).read()
            if b"\xab\xcd\xefMaxMind.com" not in data[-128 * 1024 :]:
                raise ValueError("GeoIP file is missing its MMDB metadata")
            files[edition + ".mmdb"] = data
    version = hashlib.sha256(b"".join(files.values())).hexdigest()
    for name, data in files.items():
        atomic_write(config.data_dir / "geoip" / version / name, data, 0o640)
    with database.session() as session:
        for profile in session.scalars(select(Resource).where(Resource.kind == "geo-policies")):
            profile.data, profile.version = {**profile.data, "database_version": version}, profile.version + 1
        state_set(session, "geoip_database", {"version": version, "updated_at": now()})
        operation = enqueue_apply(session)
    return {"version": version, **operation}
