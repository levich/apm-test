"""Vendor pinned upstream Lua libraries with their original licenses and hashes."""

import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/apm/integrations"
PACKAGES = {
    "crowdsec": (
        "https://codeload.github.com/crowdsecurity/lua-cs-bouncer/tar.gz/refs/tags/v1.0.19",
        ("lib/", "templates/", "LICENSE"),
    ),
    "resty-http": (
        "https://codeload.github.com/ledgetech/lua-resty-http/tar.gz/refs/tags/v0.17.1",
        ("lib/", "LICENSE"),
    ),
}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / "manifest.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    manifest = {}
    for name, (url, prefixes) in PACKAGES.items():
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if name in old and old[name]["sha256"] != digest:
            raise ValueError("Pinned upstream archive hash changed: " + name)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = Path(*Path(member.name).parts[1:])
                if not member.isfile() or ".." in relative.parts or not str(relative).startswith(prefixes):
                    continue
                target = ROOT / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        manifest[name] = {"source": url, "sha256": digest}
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Stored pinned CrowdSec and lua-resty-http sources and licenses")


if __name__ == "__main__":
    main()
