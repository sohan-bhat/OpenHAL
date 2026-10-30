"""Discovery and library matching (M3).

Every installed driver's `discover()` runs with a timeout. Drivers only send documented read-only
identify commands (WRITING-A-DRIVER rule 4). Each result is matched against the device library by
its identifiers. Matches are offered, unknown devices are listed for the driver writer.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from openhal._brand import DEVICE_FILE_SUFFIX
from openhal.drivers import registry
from openhal.drivers.base import Discovered
from openhal.spec.loader import DeviceFileError, load
from openhal.spec.models import DeviceFile

DISCOVER_TIMEOUT_S: Final = 8.0
BUNDLED_LIBRARY: Final = Path(__file__).resolve().parents[1] / "library_data"
REPO_LIBRARY: Final = Path(__file__).resolve().parents[2] / "library"


@dataclass
class Match:
    address: str
    driver: str
    identifiers: dict[str, str]
    label: str | None
    library_file: str
    device_id: str
    score: int


@dataclass
class Unknown:
    id: str
    address: str
    driver: str
    identifiers: dict[str, str]
    label: str | None


@dataclass
class DiscoveryResult:
    matched: list[Match] = field(default_factory=list)
    unknown: list[Unknown] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        return {
            "matched": [asdict(item) for item in self.matched],
            "unknown": [asdict(item) for item in self.unknown],
            "errors": self.errors,
        }


def library_paths(user_library: Path | None = None) -> list[Path]:
    """Where device files are looked up, most specific first."""
    paths = []
    if user_library is not None:
        paths.append(user_library)
    paths.extend([BUNDLED_LIBRARY, REPO_LIBRARY])
    return [path for path in paths if path.exists()]


def load_library(paths: list[Path]) -> list[tuple[Path, DeviceFile]]:
    found: list[tuple[Path, DeviceFile]] = []
    seen: set[str] = set()
    for folder in paths:
        for path in sorted(folder.rglob(f"*{DEVICE_FILE_SUFFIX}")):
            try:
                file = load(path)
            except (DeviceFileError, OSError):
                continue
            key = f"{file.device_id}:{file.device.model}"
            if key in seen:
                continue
            seen.add(key)
            found.append((path, file))
    return found


def _regex(pattern: str, value: str) -> bool:
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


def score(file: DeviceFile, found: Discovered) -> int:
    """How well a library file matches a discovered device. 0 means no match.

    A USB class or an mDNS service type only identifies the kind of device, such as any MIDI
    controller or any ESPHome node. They add to a match on a product identifier but never make one
    on their own, so a device is never offered a file for a different product of the same kind.
    """
    ids = found.identifiers
    match = file.match
    points = 0
    kind = 0
    if match.usb and ids.get("usb", "").lower() in {item.lower() for item in match.usb}:
        points += 3
    if match.usb_class and ids.get("usb_class") == match.usb_class:
        kind += 1
    if match.serial_number and "serial_number" in ids and _regex(match.serial_number, ids["serial_number"]):
        points += 2
    if match.scpi_idn and "scpi_idn" in ids and _regex(match.scpi_idn, ids["scpi_idn"]):
        points += 5
    if match.ble_name and "ble_name" in ids and _regex(match.ble_name, ids["ble_name"]):
        points += 2
    if match.ble_services:
        advertised = {item.lower() for item in ids.get("ble_services", "").split(",") if item}
        if advertised & {item.lower() for item in match.ble_services}:
            points += 2
    if match.mdns and ids.get("mdns") == match.mdns:
        kind += 1
    if match.modbus_id is not None and ids.get("modbus_id") == str(match.modbus_id):
        points += 1
    if match.homeassistant and "homeassistant" in ids and fnmatch.fnmatch(ids["homeassistant"], match.homeassistant):
        points += 3
    for section, table in (("moonraker", match.moonraker), ("esphome", match.esphome), ("firmware", match.firmware)):
        if table and all(fnmatch.fnmatch(ids.get(f"{section}.{key}", ""), value) for key, value in table.items()):
            points += 4
    if file.connect.driver != found.driver or points == 0:
        return 0
    return points + kind


async def discover(
    drivers: list[str] | None = None,
    *,
    library: list[tuple[Path, DeviceFile]] | None = None,
    registered: set[str] | None = None,
) -> DiscoveryResult:
    """Run discovery for the given drivers (default all installed) and match against the library."""
    result = DiscoveryResult()
    names = drivers or registry.names()
    entries = library if library is not None else load_library(library_paths())

    async def one(name: str) -> list[Discovered]:
        try:
            driver = registry.load(name)
        except registry.UnknownDriver as exc:
            result.errors.append({"driver": name, "error": str(exc)})
            return []
        try:
            return await asyncio.wait_for(driver.discover(), DISCOVER_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 (one driver's discovery failing doesn't stop the rest)
            result.errors.append({"driver": name, "error": f"{type(exc).__name__}: {exc}"})
            return []

    batches = await asyncio.gather(*(one(name) for name in names))
    for found in (item for batch in batches for item in batch):
        best: tuple[int, Path, DeviceFile] | None = None
        for path, file in entries:
            points = score(file, found)
            if points and (best is None or points > best[0]):
                best = (points, path, file)
        if best is not None:
            result.matched.append(
                Match(
                    found.address,
                    found.driver,
                    found.identifiers,
                    found.label,
                    str(best[1]),
                    best[2].device_id,
                    best[0],
                )
            )
        else:
            digest = hashlib.sha256(f"{found.driver}|{found.address}".encode()).hexdigest()[:10]
            result.unknown.append(Unknown(digest, found.address, found.driver, found.identifiers, found.label))
    if registered:
        result.matched = [item for item in result.matched if item.device_id not in registered]
    return result
