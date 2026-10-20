"""Maintainer command: resolve source references once and lock archive hashes."""

import concurrent.futures
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

SOURCES = {
    "openssl-ech": ("openssl/openssl", "d01cd520e52ab8bcdad27496209a27022679d970"),
    "ndk": ("vision5/ngx_devel_kit", "v0.3.3"),
    "lua": ("openresty/lua-nginx-module", "v0.10.29"),
    "stream-lua": ("openresty/stream-lua-nginx-module", "v0.0.16"),
    "headers-more": ("openresty/headers-more-nginx-module", "v0.39"),
    "brotli": ("google/ngx_brotli", "master"),
    "zstd": ("tokers/zstd-nginx-module", "master"),
    "geoip2": ("leev/ngx_http_geoip2_module", "3.4"),
    "fancyindex": ("aperezdc/ngx-fancyindex", "v0.5.2"),
}


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def resolve(item):
    name, (repo, ref) = item
    revision = json.loads(
        fetch(f"https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(ref, safe='')}")
    )["sha"]
    url = f"https://codeload.github.com/{repo}/tar.gz/{revision}"
    data = fetch(url)
    return name, {
        "repository": repo,
        "reference": ref,
        "revision": revision,
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "build/sources.lock.json"
    path.parent.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        resolved = dict(pool.map(resolve, SOURCES.items()))
    resolved["angie"] = {
        "url": "https://download.angie.software/files/angie-1.12.4.tar.gz",
        "version": "1.12.4",
        "sha256": "b236f152adb543fb6e4a94f271b873cdc0d48d570f86b1bd04435f85843f4527",
    }
    path.write_text(json.dumps(resolved, indent=2) + "\n")
    print("Locked", len(resolved), "source archives")
