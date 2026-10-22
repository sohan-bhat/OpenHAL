"""Build drivers/catalog.json from each driver package's catalog.json and drivers/planned.json.

Run `uv run python -m openhal.drivers.catalog` after adding or changing a driver. A test checks the
checked-in catalog is current. The website renders it as the supported devices page.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).parent
ROOT = PACKAGE.parents[1]
TARGET = ROOT / "drivers" / "catalog.json"
PLANNED = ROOT / "drivers" / "planned.json"
FIELDS = ("name", "tier", "status", "protocols", "families", "hazard_default", "tests", "estimate")


def entries() -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(PACKAGE.glob("*/catalog.json")):
        entry = json.loads(path.read_text())
        missing = [field for field in FIELDS if field not in entry]
        if missing:
            raise ValueError(f"{path} is missing {', '.join(missing)}.")
        found[entry["name"]] = entry
    for entry in json.loads(PLANNED.read_text()):
        found.setdefault(entry["name"], entry)
    return sorted(found.values(), key=lambda entry: (entry["tier"], entry["name"]))


def document() -> str:
    return json.dumps({"drivers": entries()}, indent=2) + "\n"


def main() -> None:
    TARGET.write_text(document())
    print(f"Wrote {TARGET} with {len(entries())} drivers")


if __name__ == "__main__":
    main()
