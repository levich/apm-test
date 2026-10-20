"""Resolve public OCI indexes without a running Docker daemon."""

import concurrent.futures
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IMAGES = {
    "python": ("registry-1.docker.io", "library/python", "3.13.15-slim-trixie", "python"),
    "uv": ("ghcr.io", "astral-sh/uv", "0.12.3", "ghcr.io/astral-sh/uv"),
    "angie": ("docker.angie.software", "angie", "1.12.4-debian", "docker.angie.software/angie"),
    "goaccess": ("registry-1.docker.io", "allinurl/goaccess", "1.12", "allinurl/goaccess"),
}
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


def resolve(item):
    name, (registry, repository, tag, image) = item
    url = f"https://{registry}/v2/{repository}/manifests/{tag}"
    headers = {"Accept": ACCEPT}
    try:
        response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40)
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        challenge = dict(re.findall(r'(\w+)="([^"]*)"', error.headers.get("WWW-Authenticate", "")))
        token_url = challenge.pop("realm") + "?" + urllib.parse.urlencode(challenge)
        with urllib.request.urlopen(token_url, timeout=40) as token_response:
            token = json.load(token_response)
        headers["Authorization"] = "Bearer " + token.get("token", token.get("access_token"))
        response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40)
    with response:
        data = response.read()
        digest = response.headers.get("Docker-Content-Digest") or "sha256:" + hashlib.sha256(data).hexdigest()
    parsed = json.loads(data)
    platforms = {
        entry["platform"]["architecture"]: entry["digest"]
        for entry in parsed.get("manifests", [])
        if entry.get("platform", {}).get("os") == "linux"
    }
    return name, {
        "tag": image + ":" + tag,
        "digest": digest,
        "reference": image + ":" + tag + "@" + digest,
        "platforms": platforms,
    }


if __name__ == "__main__":
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        pending = {pool.submit(resolve, item): item[0] for item in IMAGES.items()}
        for future in concurrent.futures.as_completed(pending):
            name = pending[future]
            try:
                key, value = future.result()
                results[key] = value
            except Exception as error:
                registry, repository, tag, image = IMAGES[name]
                results[name] = {"tag": image + ":" + tag, "verified": False, "error": type(error).__name__}
    path = Path(__file__).resolve().parents[1] / "build/images.lock.json"
    path.write_text(json.dumps(results, indent=2) + "\n")
    print(
        "OCI manifest results:", {name: value.get("digest", "unverified") for name, value in results.items()}
    )
