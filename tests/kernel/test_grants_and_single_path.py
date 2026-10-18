"""Grants and the single path to hardware (ADR 0004, threats T8, T9 and T12)."""

from __future__ import annotations

import ast
import dataclasses
import time
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import Driver, DriverInfo, Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import GrantBook, GrantError, Kernel, Write, agent
from openhal.kernel.grants import Grant
from openhal.spec import loads
from tests.kernel.conftest import FAN, AddDevice

PACKAGE = Path(__file__).resolve().parents[2] / "openhal"
PROTECTED = {"_write", "_action", "_safe_state"}


def test_grant_cannot_be_constructed() -> None:
    with pytest.raises(GrantError):
        Grant("id", "dev", "write:x", "d", time.monotonic() + 5, object())


def test_grant_book_binding() -> None:
    book = GrantBook()
    grant = book.issue("dev", "write:x", 1.0)
    with pytest.raises(GrantError, match="different value"):
        book.consume(grant, "dev", "write:x", 2.0)
    grant = book.issue("dev", "write:x", 1.0)
    with pytest.raises(GrantError, match="not dev write:y"):
        book.consume(grant, "dev", "write:y", 1.0)
    grant = book.issue("dev", "write:x", 1.0)
    with pytest.raises(GrantError):
        book.consume(grant, "other", "write:x", 1.0)
    grant = book.issue("dev", "write:x", 1.0)
    book.consume(grant, "dev", "write:x", 1.0)
    with pytest.raises(GrantError, match="already used"):
        book.consume(grant, "dev", "write:x", 1.0)
    with pytest.raises(GrantError, match="No grant"):
        book.consume("not a grant", "dev", "write:x", 1.0)


def test_grant_copies_and_foreign_books_are_rejected() -> None:
    book = GrantBook()
    other = GrantBook()
    grant = book.issue("dev", "write:x", 1.0)
    copy = dataclasses.replace(grant)
    with pytest.raises(GrantError):
        book.consume(copy, "dev", "write:x", 1.0)
    with pytest.raises(GrantError):
        other.consume(grant, "dev", "write:x", 1.0)


def test_grants_expire() -> None:
    book = GrantBook(ttl_s=0.0)
    grant = book.issue("dev", "write:x", 1.0)
    time.sleep(0.001)
    with pytest.raises(GrantError):
        book.consume(grant, "dev", "write:x", 1.0)


def test_revoke_all() -> None:
    book = GrantBook()
    keep = book.issue("a", "write:x", 1)
    drop = book.issue("b", "write:x", 1)
    book.revoke_all("b")
    with pytest.raises(GrantError):
        book.consume(drop, "b", "write:x", 1)
    book.consume(keep, "a", "write:x", 1)
    assert book.live_count() == 0


async def test_driver_refuses_without_kernel() -> None:
    driver = MockDriver(loads(FAN))
    await driver.connect()
    with pytest.raises(GrantError, match="not attached"):
        await driver.write("fan_speed", 10.0, None)
    assert driver.hardware_writes() == []


async def test_driver_refuses_bad_grants(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 10.0, None)
    wrong = kernel.grants.issue("desk-fan", "write:fan_speed", 20.0)
    with pytest.raises(GrantError):
        await driver.write("fan_speed", 10.0, wrong)
    for_action = kernel.grants.issue("desk-fan", "action:spin", {"turns": 1})
    with pytest.raises(GrantError):
        await driver.action("spin", {"turns": 99}, for_action)
    with pytest.raises(GrantError):
        await driver.safe_state(None)
    with pytest.raises(GrantError, match="already attached"):
        driver.attach(lambda *args: None)
    assert driver.hardware_writes() == []


def test_drivers_cannot_override_sealed_methods() -> None:
    with pytest.raises(TypeError, match="may not override write"):

        class Sneaky(MockDriver):  # pragma: no cover - the class body is the test
            async def write(self, channel: str, value: Any, grant: object) -> Reading | None:  # type: ignore[override]
                return await self._write(channel, value)


def test_only_the_base_class_calls_protected_methods() -> None:
    """Walk every module. Nothing outside drivers/base.py may call _write, _action or _safe_state."""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            is_call = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            if is_call and node.func.attr in PROTECTED and path.relative_to(PACKAGE).as_posix() != "drivers/base.py":
                offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno} calls {node.func.attr}")
    assert offenders == []


async def test_a_driver_that_raises_inside_write_fails_cleanly(kernel: Kernel) -> None:
    class Broken(Driver):
        info = DriverInfo(name="mock", protocols=("test",), hazard_default="low", summary="broken")

        async def connect(self) -> None:
            return None

        async def read(self, channel: str) -> Reading:
            return Reading(channel, 0.0, "percent")

        async def _write(self, channel: str, value: Any) -> Reading | None:
            raise OSError("cable unplugged")

    file = loads(FAN)
    kernel.register(file, Broken(file))
    await kernel.connect("desk-fan")
    kernel.clock.advance(60)  # type: ignore[attr-defined]
    decision = await kernel.execute(
        Write(device="desk-fan", channel="fan_speed", value="10 %"), agent("a", "control_low")
    )
    assert decision.status == "failed"
    assert "cable unplugged" in decision.message


async def test_fail_closed_on_unexpected_errors(
    kernel: Kernel, add: AddDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = await add(FAN)

    def explode(*args: Any, **kwargs: Any) -> None:
        raise ZeroDivisionError("boom")

    monkeypatch.setattr("openhal.kernel.kernel.check_rate", explode)
    decision = await kernel.execute(
        Write(device="desk-fan", channel="fan_speed", value="10 %"), agent("a", "control_low")
    )
    assert decision.status == "blocked"
    assert decision.code == "internal_error"
    assert "Nothing was sent" in decision.message
    assert driver.hardware_writes() == []
    assert kernel.audit.entries(status="blocked")[0].code == "internal_error"


def test_double_registration_rejected(kernel: Kernel) -> None:
    file = loads(FAN)
    kernel.register(file, MockDriver(file))
    with pytest.raises(ValueError, match="already registered"):
        kernel.register(file, MockDriver(file))
