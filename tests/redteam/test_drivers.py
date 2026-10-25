"""Attack family 6. Malicious drivers and the single-path guarantee (ADR 0004).

A driver reaches hardware only through the base class's `write`, `action` and `safe_state`, each of
which consumes a single-use grant the kernel issued for that exact device, target and value. A
forged, reused, expired, cross-device or cross-value grant must be refused before the mock
transport sees a byte. A deliberately malicious in-process driver that drives its own transport is
the documented residual risk (THREAT_MODEL T17), so these tests cover the structural guarantees.
"""

from __future__ import annotations

from typing import Any

import pytest

from openhal.drivers.base import GrantError
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel
from openhal.kernel.grants import Grant, GrantBook
from tests.redteam.conftest import AddDevice

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

OTHER = """
device: Other fan
id: other-fan
connect: { mock: other }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_a_grant_cannot_be_forged(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    with pytest.raises(GrantError):
        Grant(
            grant_id="x",
            device_id="desk-fan",
            target="write:fan_speed",
            digest="0" * 64,
            expires_at=1e18,
            _guard=object(),
        )
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 50.0, object())
    assert driver.hardware_writes() == []


async def test_a_grant_is_single_use(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    grant = kernel.grants.issue("desk-fan", "write:fan_speed", 50.0)
    await driver.write("fan_speed", 50.0, grant)
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 50.0, grant)
    assert driver.hardware_writes() == [("write", "fan_speed", 50.0)]


async def test_a_grant_is_bound_to_its_device_channel_and_value(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    grant = kernel.grants.issue("desk-fan", "write:fan_speed", 50.0)
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 60.0, grant)
    assert driver.hardware_writes() == []
    good = kernel.grants.issue("desk-fan", "write:fan_speed", 50.0)
    await driver.write("fan_speed", 50.0, good)
    assert driver.hardware_writes() == [("write", "fan_speed", 50.0)]


async def test_a_driver_cannot_spend_another_devices_grant(kernel: Kernel, add: AddDevice) -> None:
    fan = await add(FAN)
    other = await add(OTHER)
    for_other = kernel.grants.issue("other-fan", "write:fan_speed", 50.0)
    with pytest.raises(GrantError):
        await fan.write("fan_speed", 50.0, for_other)
    assert fan.hardware_writes() == []
    assert other.hardware_writes() == []


async def test_a_driver_cannot_name_another_device_through_its_verifier(kernel: Kernel, add: AddDevice) -> None:
    fan = await add(FAN)
    await add(OTHER)
    grant = kernel.grants.issue("other-fan", "write:fan_speed", 50.0)
    with pytest.raises(GrantError):
        fan._consume(grant, "write:fan_speed", 50.0)
    assert fan.hardware_writes() == []


async def test_a_kept_grant_cannot_be_spent_after_it_expires(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    book = GrantBook(ttl_s=0.0)
    driver._verify = book.verifier_for("desk-fan")
    stale = book.issue("desk-fan", "write:fan_speed", 50.0)
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 50.0, stale)
    assert driver.hardware_writes() == []


async def test_a_revoked_grant_is_dead(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    grant = kernel.grants.issue("desk-fan", "write:fan_speed", 50.0)
    kernel.grants.revoke_all("desk-fan")
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 50.0, grant)
    assert driver.hardware_writes() == []


async def test_a_driver_may_not_override_the_sealed_methods() -> None:
    with pytest.raises(TypeError, match="may not override"):

        class Sneaky(MockDriver):
            async def write(self, channel: str, value: Any, grant: object) -> Any:  # type: ignore[override]
                return await self._write(channel, value)

    with pytest.raises(TypeError, match="may not override"):

        class Sneaky2(MockDriver):
            def _consume(self, grant: object, target: str, value: object) -> None:  # type: ignore[override]
                return None


async def test_a_driver_cannot_reattach_to_steal_grants(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    with pytest.raises(GrantError, match="already attached"):
        driver.attach(kernel.grants.verifier_for("desk-fan"))
