"""DNS-01 adapters. Never log provider request bodies, credentials or responses."""

import fcntl
import json
import time
from contextlib import contextmanager

import dns.exception
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import httpx
import jwt

from apm.security import atomic_write, digest


class ProviderError(ValueError):
    pass


def txt_value(value):
    if value.startswith('"'):
        return b"".join(dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, value).strings).decode()
    return value


class Provider:
    provider = "base"
    supports_https_records = False

    def __init__(self, config, profile, credentials, client=None):
        self.config, self.profile, self.credentials = config, profile, credentials
        self.zone = profile["zone"].rstrip(".")
        self.zone_id = profile.get("zone_id", "")
        self.client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)

    def required(self, key):
        if not self.credentials.get(key):
            raise ProviderError(f"Missing {self.provider} credential field: {key}")
        return self.credentials[key]

    def request(self, method, url, **kwargs):
        response = self.client.request(method, url, **kwargs)
        if response.is_error:
            raise ProviderError(f"{self.provider}: HTTP {response.status_code}")
        return response

    @contextmanager
    def lock(self):
        account = self.credentials.get("username", self.zone_id or self.zone)
        filename = self.config.data_dir / "run" / f"dns-{digest(self.provider + str(account))}.lock"
        with filename.open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            yield

    def validate_name(self, name):
        name = name.rstrip(".").lower()
        if name != self.zone and not name.endswith("." + self.zone):
            raise ProviderError("Challenge is outside the configured DNS zone")
        return name

    def values(self, name):
        raise NotImplementedError

    def replace(self, name, values):
        raise NotImplementedError

    def present(self, name, value):
        name = self.validate_name(name)
        with self.lock():
            previous = self.values(name)
            existed = value in previous
            if not existed:
                self.replace(name, [*previous, value])
        return {"name": name, "value": value, "owned": not existed}

    def cleanup(self, handle):
        name = self.validate_name(handle["name"])
        if not handle.get("owned"):
            return
        with self.lock():
            previous = self.values(name)
            if handle["value"] in previous:
                self.replace(name, [v for v in previous if v != handle["value"]])

    def check(self):
        self.values("_acme-challenge." + self.zone)
        return {
            "provider": self.provider,
            "zone": self.zone,
            "read_access": True,
            "write_access": "not tested",
            "https_records": self.supports_https_records,
        }


class Yandex(Provider):
    provider = "yandex"
    supports_https_records = True
    base = "https://dns.api.cloud.yandex.net/dns/v1/zones"

    def headers(self):
        if self.credentials.get("iam_token"):
            return {"Authorization": "Bearer " + self.credentials["iam_token"]}
        if not hasattr(self, "_token"):
            current = int(time.time())
            encoded = jwt.encode(
                {
                    "aud": "https://iam.api.cloud.yandex.net/iam/v1/tokens",
                    "iss": self.required("service_account_id"),
                    "iat": current,
                    "exp": current + 600,
                },
                self.required("private_key"),
                algorithm="PS256",
                headers={"kid": self.required("key_id")},
            )
            self._token = self.request(
                "POST", "https://iam.api.cloud.yandex.net/iam/v1/tokens", json={"jwt": encoded}
            ).json()["iamToken"]
        return {"Authorization": "Bearer " + self._token}

    def read(self, name):
        if not self.zone_id:
            raise ProviderError("Yandex requires zone_id")
        response = self.client.get(
            f"{self.base}/{self.zone_id}:getRecordSet",
            params={"name": name + ".", "type": "TXT"},
            headers=self.headers(),
        )
        if response.status_code == 404:
            return None
        if response.is_error:
            raise ProviderError(f"yandex: HTTP {response.status_code}")
        return response.json()

    def values(self, name):
        self._record = self.read(name)
        return [txt_value(v) for v in (self._record or {}).get("data", [])]

    def replace(self, name, values):
        previous = self._record
        originals = {txt_value(value): value for value in (previous or {}).get("data", [])}
        additions = (
            [
                {
                    "name": name + ".",
                    "type": "TXT",
                    "ttl": str((previous or {}).get("ttl", self.profile["ttl"])),
                    "data": [originals.get(v, json.dumps(v)) for v in values],
                }
            ]
            if values
            else []
        )
        deletions = [{k: previous[k] for k in ("name", "type", "ttl", "data")}] if previous else []
        operation = self.request(
            "POST",
            f"{self.base}/{self.zone_id}:updateRecordSets",
            headers=self.headers(),
            json={"deletions": deletions, "additions": additions},
        ).json()
        if operation.get("error"):
            raise ProviderError("Yandex DNS update failed")


class Regru(Provider):
    provider = "regru"
    base = "https://api.reg.ru/api/regru2/zone/"

    def call(self, method, **params):
        data = {
            "username": self.required("username"),
            "password": self.required("password"),
            "domains": [{"dname": self.zone}],
            "output_content_type": "json",
            **params,
        }
        result = self.request(
            "POST", self.base + method, data={"input_format": "json", "input_data": json.dumps(data)}
        ).json()
        if result.get("result") != "success":
            raise ProviderError("REG.RU API operation rejected")
        return result.get("answer", {})

    def relative(self, name):
        return name[: -len(self.zone)].rstrip(".") or "@"

    def values(self, name):
        answer = self.call("get_resource_records")
        records = answer.get("domains", [{}])[0].get("rrs", [])
        return [
            r.get("content", "")
            for r in records
            if r.get("rectype") == "TXT" and r.get("subname") == self.relative(name)
        ]

    def replace(self, name, values):
        current = self.values(name)
        for value in values:
            if value not in current:
                self.call("add_txt", subdomain=self.relative(name), text=value)
        for value in current:
            if value not in values:
                self.call("remove_record", subdomain=self.relative(name), record_type="TXT", content=value)


class Webnames(Provider):
    provider = "webnames"
    base = "https://www.webnames.ru:81/RegTimeSRS.pl"

    def call(self, command, **params):
        # Caller holds account-wide flock; rate history survives worker restarts.
        history = self.config.data_dir / "run" / f"webnames-{digest(self.required('username'))}.json"
        timestamps = json.loads(history.read_text()) if history.exists() else []
        timestamps = [v for v in timestamps if v > time.time() - 1800]
        if len(timestamps) >= 60:
            time.sleep(max(0, timestamps[0] + 1801 - time.time()))
            timestamps = [v for v in timestamps if v > time.time() - 1800]
        timestamps.append(time.time())
        atomic_write(history, json.dumps(timestamps).encode())
        response = self.request(
            "POST",
            self.base,
            data={
                "thisPage": command,
                "username": self.required("username"),
                "password": self.required("password"),
                "domain_name": self.zone,
                "utf8": "1",
                **params,
            },
        ).text
        if "Error:" in response:
            raise ProviderError("Webnames API operation rejected")
        return response

    def relative(self, name):
        return name[: -len(self.zone)].rstrip(".") or "@"

    def values(self, name):
        response = self.call("pispDomainZoneInfo")
        values = []
        for line in response.splitlines():
            record = dict(part.split(":", 1) for part in line.split(";") if ":" in part)
            record = {k.strip(): v.strip() for k, v in record.items()}
            if record.get("rectype") == "TXT" and record.get("subname") == self.relative(name):
                values.append(record.get("address", ""))
        return values

    def replace(self, name, values):
        current = self.values(name)
        for value in values:
            if value not in current:
                self.call("pispDomainZoneAddTXT", subname=self.relative(name), text=value)
        for value in current:
            if value not in values:
                self.call("pispDomainZoneRmRR", subname=self.relative(name), rectype="TXT", address=value)
        self.call("pispDomainZoneUpdate")

    def check(self):
        with self.lock():
            return super().check()


class Selectel(Provider):
    provider = "selectel"
    supports_https_records = True
    base = "https://api.selectel.ru/domains/v2"

    def headers(self):
        if self.credentials.get("token"):
            return {"X-Auth-Token": self.credentials["token"]}
        if not hasattr(self, "_token"):
            response = self.request(
                "POST",
                "https://cloud.api.selcloud.ru/identity/v3/auth/tokens",
                json={
                    "auth": {
                        "identity": {
                            "methods": ["password"],
                            "password": {
                                "user": {
                                    "name": self.required("username"),
                                    "domain": {"name": self.required("domain_name")},
                                    "password": self.required("password"),
                                }
                            },
                        },
                        "scope": {"project": {"id": self.required("project_id")}},
                    }
                },
            )
            self._token = response.headers["X-Subject-Token"]
        return {"X-Auth-Token": self._token}

    def values(self, name):
        if not self.zone_id:
            raise ProviderError("Selectel requires zone_id")
        result = self.request(
            "GET",
            f"{self.base}/zones/{self.zone_id}/rrset",
            headers=self.headers(),
            params={"name": name + ".", "rrset_types": "TXT", "limit": 1000},
        ).json()
        records = result.get("result", [])
        self._record = next(
            (r for r in records if r["name"].rstrip(".") == name and r["type"] == "TXT"), None
        )
        return [txt_value(r["content"]) for r in (self._record or {}).get("records", [])]

    def replace(self, name, values):
        previous = self._record
        base = f"{self.base}/zones/{self.zone_id}/rrset"
        if not values:
            if previous:
                self.request("DELETE", f"{base}/{previous['id']}", headers=self.headers())
            return
        originals = {txt_value(record["content"]): record for record in (previous or {}).get("records", [])}
        payload = {
            "name": name + ".",
            "ttl": (previous or {}).get("ttl", self.profile["ttl"]),
            "type": "TXT",
            "records": [originals.get(v, {"content": json.dumps(v), "disabled": False}) for v in values],
        }
        self.request(
            "PATCH" if previous else "POST",
            f"{base}/{previous['id']}" if previous else base,
            headers=self.headers(),
            json=payload,
        )


class Cloudru(Provider):
    provider = "cloudru"
    base = "https://dns.api.cloud.ru/v1"

    def headers(self):
        if self.credentials.get("token"):
            return {"Authorization": "Bearer " + self.credentials["token"]}
        if not hasattr(self, "_token"):
            self._token = self.request(
                "POST",
                "https://iam.api.cloud.ru/api/v1/auth/token",
                json={"keyId": self.required("key_id"), "secret": self.required("secret")},
            ).json()["access_token"]
        return {"Authorization": "Bearer " + self._token}

    def records(self):
        if not self.zone_id:
            raise ProviderError("Cloud.ru Evolution requires zone_id")
        records, token = [], ""
        while True:
            result = self.request(
                "GET",
                f"{self.base}/publicRecordsSole",
                headers=self.headers(),
                params={"publicZoneId": self.zone_id, "pageSize": 100, "pageToken": token},
            ).json()
            records.extend(result.get("records", []))
            token = result.get("nextPageToken", "")
            if not token:
                return records

    def values(self, name):
        relative = name[: -len(self.zone)].rstrip(".")
        self._record = next(
            (
                r
                for r in self.records()
                if r.get("type") == "TXT" and r.get("name", "").rstrip(".") in (name, relative)
            ),
            None,
        )
        return [txt_value(v) for v in (self._record or {}).get("values", [])]

    def replace(self, name, values):
        previous = self._record
        base = f"{self.base}/publicRecordsSole"
        if not values:
            if previous:
                self.request("DELETE", f"{base}/{previous['id']}", headers=self.headers())
            return
        originals = {txt_value(value): value for value in (previous or {}).get("values", [])}
        payload = {
            "values": [originals.get(v, json.dumps(v)) for v in values],
            "ttl": (previous or {}).get("ttl", self.profile["ttl"]),
        }
        if not previous:
            payload.update(publicZoneId=self.zone_id, name=name[: -len(self.zone)].rstrip("."), type="TXT")
        operation = self.request(
            "PATCH" if previous else "POST",
            f"{base}/{previous['id']}" if previous else base,
            headers=self.headers(),
            json=payload,
        ).json()
        if operation.get("error"):
            raise ProviderError("Cloud.ru DNS operation failed")


PROVIDERS = {p.provider: p for p in (Yandex, Regru, Webnames, Selectel, Cloudru)}


def provider_for(config, profile, credentials, client=None):
    return PROVIDERS[profile["provider"]](config, profile, credentials, client)


def wait_propagation(name, value, timeout=600):
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5
    zone = name.rstrip(".").split(".")
    nameservers = []
    for i in range(len(zone) - 1):
        try:
            nameservers = [str(answer.target) for answer in resolver.resolve(".".join(zone[i:]), "NS")]
            break
        except dns.exception.DNSException:
            continue
    if not nameservers:
        raise ProviderError("Cannot locate authoritative DNS servers")
    addresses = []
    for server in nameservers:
        for family in ("A", "AAAA"):
            try:
                addresses.extend(str(answer) for answer in resolver.resolve(server, family))
            except dns.exception.DNSException:
                pass
    if not addresses:
        raise ProviderError("Cannot resolve authoritative DNS servers")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        confirmed = 0
        for server in addresses:
            query = dns.resolver.Resolver(configure=False)
            query.nameservers, query.lifetime = [server], 5
            try:
                if value in [b"".join(answer.strings).decode() for answer in query.resolve(name, "TXT")]:
                    confirmed += 1
            except dns.exception.DNSException:
                pass
        if confirmed == len(addresses):
            return
        time.sleep(3)
    raise ProviderError("TXT propagation deadline exceeded")
