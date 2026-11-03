"""Download the SO-101 model and the studio HDRI that the film scenes use.

Every file in video/assets.json is fetched from its pinned URL into video/assets/
and checked against its SHA-256. Files already present with the right hash are
kept. Run it with any Python 3.11 or newer, for example

    python3 -I video/scenes/fetch_assets.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

VIDEO = Path(__file__).resolve().parent.parent
MANIFEST = VIDEO / "assets.json"
ASSETS = VIDEO / "assets"
STRIP = {"so101": "Simulation/SO101/"}


def sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def target(group: str, name: str) -> Path:
    """Map a manifest entry to its path under video/assets."""
    prefix = STRIP.get(group, "")
    local = name[len(prefix) :] if prefix and name.startswith(prefix) else name
    return ASSETS / group / local


def fetch(url: str, dest: Path, expected: str) -> None:
    """Download one file to dest and delete it if the hash differs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    curl = shutil.which("curl")
    if curl:
        subprocess.run([curl, "-fsSL", "--retry", "3", "-o", str(partial), url], check=True)  # noqa: S603
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "openhal-video-fetch"})  # noqa: S310
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:  # noqa: S310
            while block := response.read(1 << 20):
                out.write(block)
    actual = sha256(partial)
    if actual != expected:
        partial.unlink()
        raise SystemExit(f"hash mismatch for {url}: expected {expected}, got {actual}")
    partial.replace(dest)


def main() -> int:
    """Fetch every asset in the manifest."""
    manifest = json.loads(MANIFEST.read_text())
    for group, spec in manifest.items():
        for name, expected in spec["files"].items():
            dest = target(group, name)
            if dest.exists() and sha256(dest) == expected:
                continue
            url = f"{spec['base']}/{name}"
            print(f"fetch {url}")
            fetch(url, dest, expected)
    print(f"assets ready in {ASSETS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
