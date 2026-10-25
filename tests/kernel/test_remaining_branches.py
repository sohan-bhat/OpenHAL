"""Kernel branches the behavior tests don't reach on their own.

Run history replay after a restart, expressions that name no device or an unknown one, the safe
state as a rate reference when it has several steps, grant checks for the wrong device, grant
expiry, and a confirmation queue with nobody listening.
"""

from __future__ import annotations

import time

import pytest

from openhal.audit.log import AuditLog
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, GrantBook, GrantError, Kernel, Write, human
from openhal.kernel import kernel as kernel_module
from openhal.kernel.checks import check_rate
from openhal.kernel.confirmations import ConfirmationQueue
from openhal.spec import loads
from tests.kernel.conftest import AddDevice, FakeClock
from tests.kernel.test_action_runs import WATERER, water

PERSON = human("sohan")
KEY = b"test-approval-key-32-bytes-long!"


async def _first_kernel(audit: AuditLog, clock: FakeClock) -> MockDriver:
    kernel = Kernel(audit, clock=clock, approval_key=KEY)
    file = loads(WATERER)
    driver = MockDriver(file)
    kernel.register(file, driver)
    await kernel.connect("waterer")
    for request in (water(5), water(5), water(120), Action(device="waterer", action="stop")):
        clock.advance(2)
        kernel.note_reading("waterer", await driver.read("tank"))
        await kernel.execute(request, PERSON)
    return driver


async def _second_kernel(audit: AuditLog, clock: FakeClock) -> tuple[Kernel, MockDriver]:
    kernel = Kernel(audit, clock=clock, approval_key=KEY)
    file = loads(WATERER)
    driver = MockDriver(file)
    kernel.register(file, driver)
    await kernel.connect("waterer")
    return kernel, driver


async def test_a_restart_counts_only_finished_runs_of_limited_actions(clock: FakeClock) -> None:
    audit = AuditLog(":memory:")
    await _first_kernel(audit, clock)
    kernel, driver = await _second_kernel(audit, clock)
    clock.advance(2)
    kernel.note_reading("waterer", await driver.read("tank"))
    assert (await kernel.execute(water(5), PERSON)).status == "done"
    clock.advance(2)
    kernel.note_reading("waterer", await driver.read("tank"))
    assert (await kernel.execute(water(5), PERSON)).code == "rate_limited"


async def test_a_restart_forgets_runs_older_than_the_window(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    audit = AuditLog(":memory:")
    await _first_kernel(audit, clock)
    later = time.time() + 7200
    with monkeypatch.context() as patch:
        patch.setattr(kernel_module.time, "time", lambda: later)
        kernel, driver = await _second_kernel(audit, clock)
    for _ in range(3):
        clock.advance(2)
        kernel.note_reading("waterer", await driver.read("tank"))
        assert (await kernel.execute(water(5), PERSON)).status == "done"


def test_hub_expressions_read_bare_names_as_words_and_unknown_devices_as_unknown(kernel: Kernel) -> None:
    assert kernel.evaluate_expression("tank == ok") is False
    assert kernel.evaluate_expression("ghost.tank == ok") is None


DRIVE = """
device: Conveyor
id: conveyor
connect: { mock: conveyor }
write:
  speed: { unit: "%", min: 0, max: 100, max_change_per_s: 5 }
actions:
  halt: {}
safe_state:
  - action: halt
  - { speed: 10 }
hazard: low
confirmed: { by: sohan, at: 2026-10-24 }
"""


async def test_rate_reference_skips_safe_state_steps_for_other_targets(kernel: Kernel, add: AddDevice) -> None:
    await add(DRIVE, settle=1.0, fail_reads=True)
    near = await kernel.execute(Write(device="conveyor", channel="speed", value=14, unit="%"), PERSON)
    assert near.status == "done", near.message
    far = await kernel.execute(Write(device="conveyor", channel="speed", value=60, unit="%"), PERSON)
    assert far.code == "rate_limited"


def test_check_rate_without_a_rate_or_reference_allows_anything() -> None:
    check_rate("speed", "%", None, 100.0, 0.0, 1.0)
    check_rate("speed", "%", 5.0, 100.0, None, 1.0)


def test_a_driver_verifier_refuses_other_devices() -> None:
    book = GrantBook()
    verify = book.verifier_for("waterer")
    grant = book.issue("lamp", "write:level", 1.0)
    with pytest.raises(GrantError, match="belongs to waterer, not lamp"):
        verify(grant, "lamp", "write:level", 1.0)


def test_expired_grants_leave_the_live_count() -> None:
    book = GrantBook(ttl_s=0.0)
    book.issue("waterer", "action:water", {"duration": 5.0})
    time.sleep(0.001)
    assert book.live_count() == 0


async def test_a_queue_without_a_listener_still_expires_requests(kernel: Kernel, add: AddDevice) -> None:
    await add(WATERER)
    queue = ConfirmationQueue(ttl_s=1.0)
    request = water(5)
    queue.add(request, PERSON, kernel.evaluate(request, PERSON), now=0.0)
    expired = queue.expire(now=2.0)
    assert [item.status for item in expired] == ["expired"]
    assert expired[0].history == ["expired"]
