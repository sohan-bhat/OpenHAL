"""Devices `openhal init` offers to add, from discovery and from addresses the person names.

A library match is copied from the device library with the address discovery found. A
self-describing device, an OpenHAL firmware board or an ESPHome node, is asked to describe itself
with its driver's read-only commands. Either way every limit is marked suggested and every
confirmation is dropped, so the file loads read-only until a person checks and confirms it.
Nothing here writes to a device.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from openhal._brand import DEVICE_FILE_SUFFIX, SPEC_VERSION
from openhal.drivers import registry
from openhal.drivers.base import Driver
from openhal.hub import discovery
from openhal.spec.loader import DeviceFileError, from_data, load, parse_yaml
from openhal.spec.models import PRIMARY_PARAM, DeviceFile
from openhal.writer.engine import force_suggested

SELF_DESCRIBING: Final = ("openhal-firmware", "esphome")
DESCRIBE_TIMEOUT_S: Final = 10.0
TOOL: Final = "openhal init"

Discover = Callable[[list[str] | None, set[str]], Awaitable[discovery.DiscoveryResult]]


@dataclass
class Offer:
    """One device init can add, with the device file it would save, or the reason it can't."""

    driver: str
    address: str
    label: str
    source: str
    data: dict[str, Any] | None = None
    problem: str | None = None


@dataclass
class Found:
    offers: list[Offer] = field(default_factory=list)
    unknown: list[Offer] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    skipped_drivers: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Existing:
    """Device files already in the devices folder, by id and by driver and address."""

    ids: set[str] = field(default_factory=set)
    addresses: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def scan(cls, folder: Path) -> Existing:
        existing = cls()
        for path in sorted(folder.glob(f"*{DEVICE_FILE_SUFFIX}")) if folder.exists() else []:
            try:
                file = load(path)
            except (DeviceFileError, OSError):
                continue
            existing.add(file)
        return existing

    def add(self, file: DeviceFile) -> None:
        self.ids.add(file.device_id)
        primary = PRIMARY_PARAM.get(file.connect.driver, "target")
        address = file.connect.params.get(primary)
        if address is not None:
            self.addresses.add((file.connect.driver, str(address)))

    def has(self, driver: str, address: str) -> bool:
        if (driver, address) in self.addresses:
            return True
        host, sep, _ = address.rpartition(":")
        return bool(sep) and (driver, host) in self.addresses


def _short_connect(driver: str, params: dict[str, Any]) -> dict[str, Any]:
    primary = PRIMARY_PARAM.get(driver, "target")
    rest = {key: value for key, value in params.items() if key != primary}
    return {driver: params.get(primary, "auto"), **rest} if primary in params else {"driver": driver, **rest}


def _finish(data: dict[str, Any], source: str) -> dict[str, Any]:
    cleaned = force_suggested(data)
    provenance = cleaned.get("provenance")
    provenance = dict(provenance) if isinstance(provenance, dict) else {}
    provenance.setdefault("source", source)
    provenance["tool"] = TOOL
    cleaned["provenance"] = provenance
    ordered: dict[str, Any] = {"openhal": cleaned.pop("openhal", SPEC_VERSION), "device": cleaned.pop("device")}
    ordered.update(cleaned)
    return ordered


def from_library(match: discovery.Match) -> Offer:
    """The library file for a match, with the address discovery found and nothing confirmed."""
    label = match.label or match.device_id
    offer = Offer(match.driver, match.address, label, "library")
    try:
        data = parse_yaml(Path(match.library_file).read_text(encoding="utf-8"))
        file = from_data(data)
    except (DeviceFileError, OSError) as exc:
        offer.problem = f"The library file {match.library_file} didn't load. {exc}"
        return offer
    params = {**file.connect.params, **registry.connect_params(match.driver, match.address)}
    data["connect"] = _short_connect(file.connect.driver, params)
    offer.data = _finish(data, "library")
    return offer


async def describe(driver_name: str, address: str, *, timeout_s: float = DESCRIBE_TIMEOUT_S) -> dict[str, Any]:
    """Ask a self-describing device what it has, with its driver's read-only commands."""
    driver_class = registry.load(driver_name)
    params = registry.connect_params(driver_name, address)
    probe = from_data({"device": "Device being described", "connect": {"driver": driver_name, "params": params}})
    instance: Driver = driver_class(probe)
    try:
        await asyncio.wait_for(instance.connect(), timeout_s)
        described = await asyncio.wait_for(instance.describe(), timeout_s)
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(instance.close(), 5.0)
    if not described:
        raise ValueError(f"The {driver_name} driver couldn't describe the device at {address}.")
    data = dict(described)
    device = data.pop("device", None)
    name = device.get("name") if isinstance(device, dict) else None
    source = "self-described" if driver_name == "openhal-firmware" else "driver-describe"
    return _finish({"device": name or "New device", "connect": _short_connect(driver_name, params), **data}, source)


async def describe_offer(driver: str, address: str, label: str | None = None) -> Offer:
    offer = Offer(driver, address, label or f"{driver} device", "self-described")
    try:
        offer.data = await describe(driver, address)
        offer.label = label or str(offer.data["device"])
    except Exception as exc:  # noqa: BLE001 (a device that can't describe itself is reported, not fatal)
        primary = PRIMARY_PARAM.get(driver, "target")
        offer.problem = (
            f"It didn't describe itself ({type(exc).__name__}: {exc}). Try openhal writer start "
            f"--driver {driver} --param {primary}={address}"
        )
    return offer


def _missing_extra(error: str) -> bool:
    return "optional dependency" in error


async def find(
    existing: Existing,
    *,
    discover: bool,
    drivers: list[str] | None = None,
    known: list[tuple[str, str]] | None = None,
    run_discovery: Discover | None = None,
) -> Found:
    """Everything init can offer. Devices that already have a device file are left out."""
    found = Found()
    seen: set[tuple[str, str]] = set()

    def fresh(driver: str, address: str) -> bool:
        if (driver, address) in seen:
            return False
        seen.add((driver, address))
        if existing.has(driver, address):
            found.kept.append(f"{driver} at {address}")
            return False
        return True

    describing: list[Awaitable[Offer]] = []
    if discover:
        runner = run_discovery or _discover
        result = await runner(drivers, existing.ids)
        for error in result.errors:
            if _missing_extra(error.get("error", "")):
                found.skipped_drivers.append(error.get("driver", "?"))
            else:
                found.errors.append(f"{error.get('driver', '?')}  {error.get('error', '')}")
        for match in result.matched:
            if fresh(match.driver, match.address):
                found.offers.append(from_library(match))
        for unknown in result.unknown:
            if not fresh(unknown.driver, unknown.address):
                continue
            label = unknown.label or unknown.address
            if unknown.driver in SELF_DESCRIBING:
                describing.append(describe_offer(unknown.driver, unknown.address, label))
            else:
                found.unknown.append(Offer(unknown.driver, unknown.address, label, "unknown"))
    for driver, address in known or []:
        if driver not in SELF_DESCRIBING:
            found.errors.append(
                f"{driver}  only self-describing devices can be added by address ({', '.join(SELF_DESCRIBING)}). "
                f"Use openhal writer start --driver {driver}"
            )
            continue
        if fresh(driver, address):
            describing.append(describe_offer(driver, address))
    found.offers.extend(await asyncio.gather(*describing))
    return found


async def _discover(drivers: list[str] | None, registered: set[str]) -> discovery.DiscoveryResult:
    return await discovery.discover(drivers, registered=registered)


def save(offer: Offer, folder: Path, existing: Existing) -> Path:
    """Save an offer's device file under an id and file name nothing else uses."""
    if offer.data is None:
        raise ValueError(offer.problem or "There is no device file to save.")
    data = dict(offer.data)
    file = from_data(data)
    base = file.device_id
    device_id, number = base, 2
    while device_id in existing.ids or (folder / f"{device_id}{DEVICE_FILE_SUFFIX}").exists():
        device_id = f"{base[:44]}-{number}"
        number += 1
    ordered: dict[str, Any] = {"openhal": data.pop("openhal"), "device": data.pop("device"), "id": device_id}
    data.pop("id", None)
    ordered.update(data)
    saved = from_data(ordered)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{device_id}{DEVICE_FILE_SUFFIX}"
    path.write_text(yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    existing.add(saved)
    return path
