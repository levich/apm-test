"""Fetch pinned frontend distributions; record SHA-256 and retain licenses."""

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/apm/static/vendor"
ASSETS = {
    "tabler.min.css": "https://cdn.jsdelivr.net/npm/@tabler/core@1.6.0/dist/css/tabler.min.css",
    "tabler.min.js": "https://cdn.jsdelivr.net/npm/@tabler/core@1.6.0/dist/js/tabler.min.js",
    "htmx.min.js": "https://cdn.jsdelivr.net/npm/htmx.org@2.0.11/dist/htmx.min.js",
    "swagger-ui-bundle.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.30.1/swagger-ui-bundle.js",
    "swagger-ui.css": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.30.1/swagger-ui.css",
    "TABLER-LICENSE": "https://raw.githubusercontent.com/tabler/tabler/@tabler/core@1.6.0/LICENSE",
    "ICONS-LICENSE": "https://raw.githubusercontent.com/tabler/tabler-icons/v3.34.1/LICENSE",
    "HTMX-LICENSE": "https://cdn.jsdelivr.net/npm/htmx.org@2.0.11/LICENSE",
    "SWAGGER-LICENSE": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.30.1/LICENSE",
}


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in ASSETS.items():
        print(name, flush=True)
        try:
            data = fetch(url)
        except urllib.error.HTTPError as error:
            if error.code != 404 or "LICENSE" not in name:
                raise
            url += ".md"
            data = fetch(url)
        if name.endswith(".css"):
            # Fonts use the system stack; never contact a font CDN from an admin panel.
            data = re.sub(rb'@import\s+(?:url\([^)]*\)|["\'][^"\']*["\'])\s*;', b"", data)
            data = re.sub(rb"/\*# sourceMappingURL=.*?\*/", b"", data)
        if name.endswith(".js"):
            data = re.sub(rb"//# sourceMappingURL=.*", b"", data)
        (ROOT / name).write_bytes(data)
        manifest[name] = {"source": url, "sha256": hashlib.sha256(data).hexdigest()}
    icons = []
    for name in ("server", "shield", "settings", "dashboard"):
        url = f"https://cdn.jsdelivr.net/npm/@tabler/icons@3.34.1/icons/outline/{name}.svg"
        source = fetch(url).decode()
        body = source[source.find(">") + 1 : source.rfind("</svg>")]
        icons.append(
            f'<symbol id="{name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">{body}</symbol>'
        )
        manifest[f"icon:{name}"] = {"source": url, "sha256": hashlib.sha256(source.encode()).hexdigest()}
    (ROOT / "icons.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg">' + "".join(icons) + "</svg>")
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Stored {len(manifest)} pinned frontend artifacts")


if __name__ == "__main__":
    main()
