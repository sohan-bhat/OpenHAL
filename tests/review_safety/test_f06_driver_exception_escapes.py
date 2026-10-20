"""F06 (high). A driver exception outside DriverError, OSError and TimeoutError escapes execute().

The hardware was changed, but the kernel writes no audit entry, does not update its state, and
raises into the caller instead of returning a decision (SAFETY.md guarantees 5 and 6).
"""

from __future__ import annotations

from typing import Any

import pytest

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel, Write, agent
from openhal.spec import loads
from tests.kernel.conftest import FAN, FakeClock


class BadReplyDriver(MockDriver):
    """Sends the command, then fails to parse the device's reply. A common driver bug."""

    async def _write(self, channel: str, value: Any) -> Reading | None:
        await super()._write(channel, value)
        raise ValueError("could not parse reply 'OK\\r\\n?'")


async def test_f06_unexpected_driver_error_is_contained_and_logged(kernel: Kernel, clock: FakeClock) -> None:
    file = loads(FAN)
    driver = BadReplyDriver(file)
    kernel.register(file, driver)
    await kernel.connect("desk-fan")
    clock.advance(60)

    try:
        decision = await kernel.execute(
            Write(device="desk-fan", channel="fan_speed", value="40 %"), agent("a", "control_low")
        )
    except Exception as exc:  # noqa: BLE001
        writes = kernel.audit.entries(event="write")
        pytest.fail(
            f"execute raised {exc!r} after the hardware changed to {driver.values['fan_speed']} %. "
            f"Audit write entries: {len(writes)}"
        )
    assert decision.status in ("failed", "blocked")
    assert kernel.audit.entries(event="write"), "the write that reached hardware is not in the audit log"
