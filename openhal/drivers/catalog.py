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


DEFAULT_CONFORMANCE = "control"


def conformance_for(entry: dict[str, Any]) -> str:
    """The protocol level a driver declares (ADR 0015).

    A package catalog entry may state it. Otherwise it comes from the driver's DriverInfo, and a
    driver that can't be imported, or a planned one, gets the default level.
    """
    declared = entry.get("conformance")
    if isinstance(declared, str):
        return declared
    from openhal.drivers import registry

    try:
        return registry.load(entry["name"]).info.conformance
    except registry.UnknownDriver:
        return DEFAULT_CONFORMANCE


def entries() -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(PACKAGE.glob("*/catalog.json")):
        entry = json.loads(path.read_text())
        missing = [field for field in FIELDS if field not in entry]
        if missing:
            raise ValueError(f"{path} is missing {', '.join(missing)}.")
        found[entry["name"]] = {**entry, "conformance": conformance_for(entry)}
    for entry in json.loads(PLANNED.read_text()):
        found.setdefault(entry["name"], {**entry, "conformance": entry.get("conformance", DEFAULT_CONFORMANCE)})
    return sorted(found.values(), key=lambda entry: (entry["tier"], entry["name"]))


def document() -> str:
    return json.dumps({"drivers": entries()}, indent=2) + "\n"


README = ROOT / "README.md"
START, END = "<!-- devices:start -->", "<!-- devices:end -->"
STATUS = {
    "implemented": "tested on simulator",
    "verified": "verified on hardware",
    "stub": "stub",
    "planned": "planned",
}


def readme_table() -> str:
    """The supported devices table for README.md. Real drivers only, planned ones on one line."""
    rows = ["| Driver | Devices covered | Status | Hazard default |", "|---|---|---|---|"]
    planned = []
    for entry in entries():
        if entry["tier"] == 0:
            continue
        if entry["status"] == "planned":
            planned.append(f"`{entry['name']}`")
            continue
        families = ", ".join(entry["families"][:3])
        status = STATUS.get(entry["status"], entry["status"])
        rows.append(f"| `{entry['name']}` | {families} | {status} | {entry['hazard_default']} |")
    lines = [START, *rows]
    if planned:
        lines += ["", "Planned: " + ", ".join(planned) + "."]
    return "\n".join([*lines, END])


def readme_with_table(text: str) -> str:
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    return head + readme_table() + tail


def main() -> None:
    TARGET.write_text(document())
    if README.exists() and START in README.read_text():
        README.write_text(readme_with_table(README.read_text()))
    print(f"Wrote {TARGET} with {len(entries())} drivers")


if __name__ == "__main__":
    main()
