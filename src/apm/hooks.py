import json
import os
import sys

from apm.config import Settings
from apm.db import Database, Resource, now, state_get, state_set
from apm.dns import provider_for, wait_propagation
from apm.security import Vault, digest


def execute(action, config=None):
    config = config or Settings()
    database = Database(config)
    certificate_id = os.environ["APM_CERTIFICATE_ID"]
    domain = os.environ.get("CERTBOT_IDENTIFIER", os.environ.get("CERTBOT_DOMAIN", "")).removeprefix("*.")
    value = os.environ["CERTBOT_VALIDATION"]
    name = "_acme-challenge." + domain
    key = "challenge:" + digest(certificate_id + name + value)
    with database.session() as session:
        cert = session.get(Resource, certificate_id)
        profile = session.get(Resource, cert.data["dns_profile_id"])
        provider = provider_for(config, profile.data, Vault(config.data_dir).decrypt(profile.secret))
        handle = state_get(session, key, {})
    if action == "auth":
        # Write ownership intent before the external mutation so cleanup survives crashes.
        with provider.lock():
            owned = value not in provider.values(name)
        handle = {
            "name": name,
            "value": value,
            "owned": owned,
            "profile_id": profile.id,
            "certificate_id": certificate_id,
            "created_at": now(),
        }
        with database.session() as session:
            state_set(session, key, handle)
        provider.present(name, value)
        wait_propagation(name, value, profile.data["propagation_timeout"])
    elif action == "cleanup":
        if handle:
            provider.cleanup(handle)
            with database.session() as session:
                state_set(session, key, {**handle, "cleaned": True})
    else:
        raise ValueError("Unknown hook action")
    return {"ok": True}


if __name__ == "__main__":
    try:
        print(json.dumps(execute(sys.argv[1])))
    except Exception as error:
        print(f"DNS hook failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
