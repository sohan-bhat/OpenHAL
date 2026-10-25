"""The knx driver's conformance case, through a fake KNXnet/IP tunneling server with a simulated room."""

from __future__ import annotations

import asyncio
import time

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.knx.driver import KnxDriver
from openhal.drivers.knx.simulator import KnxGatewaySim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

ROOM = """
read:
  temperature: { unit: degC, range: [-10, 50], map: { group_address: 2/1/1, dpt: "9.001" } }
write:
  setpoint: { unit: degC, min: 5, max: 30, map: { group_address: 2/1/2, dpt: "9.001", state_address: 2/1/3 } }
  light: { type: bool, map: { group_address: 1/1/1, dpt: "1.001", state_address: 1/1/2 } }
  hvac_mode:
    type: enum
    values: [auto, comfort, standby, economy, building_protection]
    map: { group_address: 2/1/4, dpt: "20.102" }
safe_state: { light: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(gateway: KnxGatewaySim, *, channels: str = ROOM, timeout: str = "1 s") -> DeviceFile:
    connect = f"{{ knx: 127.0.0.1, port: {gateway.port}, local_ip: 127.0.0.1, timeout: {timeout} }}"
    return loads(f"device: Conformance room\nid: conformance-knx\nconnect: {connect}\n{channels}")


async def wait_disconnected(driver: Driver) -> None:
    deadline = time.monotonic() + 3.0
    while (await driver.health()).connected:
        if time.monotonic() > deadline:
            raise AssertionError("the driver did not notice the tunnel closing")
        await asyncio.sleep(0.02)


def case() -> ConformanceCase:
    gateway = KnxGatewaySim().start()

    async def broken(driver: Driver) -> None:
        gateway.kick()
        await wait_disconnected(driver)

    async def cleanup() -> None:
        gateway.stop()

    return ConformanceCase(
        name="knx", file=device_file(gateway), make=KnxDriver, break_connection=broken, cleanup=cleanup
    )
