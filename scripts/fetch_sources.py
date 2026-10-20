import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads(Path("build/sources.lock.json").read_text())
for name, source in manifest.items():
    with urllib.request.urlopen(source["url"], timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError("Source hash mismatch: " + name)
    destination = root / name
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            member.name = str(Path(*Path(member.name).parts[1:]))
            if member.name == ".":
                continue
            archive.extract(member, destination, filter="data")
    print("Verified", name, flush=True)
