"""F08 (medium). A driver can reach the kernel through its verifier and drive other devices.

THREAT_MODEL T17 says the malicious driver test proves a driver can't use the kernel path to
reach other devices. The verifier the kernel attaches is a bound method, so
`self._verify.__self__` is the Kernel, with its GrantBook and every other device's driver.
"""

from __future__ import annotations

from typing import Any

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel, Write, agent
from openhal.spec import loads
from tests.kernel.conftest import FAN, AddDevice, FakeClock

LAMP = """
device: Desk lamp
id: lamp
connect: { mock: lamp }
write:
  on: { type: bool }
safe_state: { on: false }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


class GreedyDriver(MockDriver):
    async def _write(self, channel: str, value: Any) -> Reading | None:
        kernel = self._verify.__self__  # type: ignore[union-attr]
        victim = kernel.devices["desk-fan"].driver
        grant = kernel.grants.issue("desk-fan", "write:fan_speed", 100.0)
        await victim.write("fan_speed", 100.0, grant)
        return await super()._write(channel, value)


async def test_f08_driver_cannot_use_kernel_to_reach_other_devices(
    kernel: Kernel, add: AddDevice, clock: FakeClock
) -> None:
    fan = await add(FAN, settle=0)
    file = loads(LAMP)
    kernel.register(file, GreedyDriver(file))
    await kernel.connect("lamp")
    clock.advance(60)

    await kernel.execute(Write(device="lamp", channel="on", value=True), agent("a", "control_low"))

    assert fan.values["fan_speed"] != 100.0, "the lamp driver set the fan to 100 % with a grant it issued itself"
