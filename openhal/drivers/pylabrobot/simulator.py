"""A recording PyLabRobot backend for tests and the conformance case.

It is PyLabRobot's own LiquidHandlerChatterboxBackend, which accepts every operation and prints
it, with the printing captured, every operation recorded, and fault hooks. PyLabRobot's
LiquidHandler still does its own checks and tip and volume tracking, so the driver runs against
the real front end of the library.

Fault hooks. `fail_next` makes the next operation raise like a firmware error, `latency_s`
slows every operation, and `lost` makes every call fail like an unplugged instrument.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from collections.abc import Awaitable, Callable
from typing import Any

from pylabrobot.liquid_handling.backends.chatterbox import (  # type: ignore[import-untyped]
    LiquidHandlerChatterboxBackend,
)


class InstrumentError(RuntimeError):
    """Stands in for a firmware error from a real liquid handler."""


class RecordingBackend(LiquidHandlerChatterboxBackend):  # type: ignore[misc]
    """Chatterbox, recorded and with faults."""

    def __init__(self, num_channels: int = 8) -> None:
        super().__init__(num_channels=num_channels)
        self.operations: list[tuple[str, list[str], list[float]]] = []
        self.printed = io.StringIO()
        self.fail_next = 0
        self.latency_s = 0.0
        self.lost = False

    async def _run(self, name: str, ops: list[Any], call: Callable[[], Awaitable[Any]]) -> Any:
        if self.lost:
            raise InstrumentError("The instrument doesn't answer. Check the USB cable.")
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.fail_next > 0:
            self.fail_next -= 1
            raise InstrumentError(f"{name} failed on the instrument (simulated firmware error).")
        names = [getattr(getattr(op, "resource", None), "name", "") for op in ops]
        volumes = [float(getattr(op, "volume", 0.0) or 0.0) for op in ops]
        self.operations.append((name, names, volumes))
        with contextlib.redirect_stdout(self.printed):
            return await call()

    async def setup(self) -> None:
        parent = super().setup
        await self._run("setup", [], lambda: parent())

    async def stop(self) -> None:
        with contextlib.redirect_stdout(self.printed):
            await super().stop()

    async def pick_up_tips(self, ops: list[Any], use_channels: list[int], **kwargs: Any) -> None:
        parent = super().pick_up_tips
        await self._run("pick_up_tips", ops, lambda: parent(ops, use_channels, **kwargs))

    async def drop_tips(self, ops: list[Any], use_channels: list[int], **kwargs: Any) -> None:
        parent = super().drop_tips
        await self._run("drop_tips", ops, lambda: parent(ops, use_channels, **kwargs))

    async def aspirate(self, ops: list[Any], use_channels: list[int], **kwargs: Any) -> None:
        parent = super().aspirate
        await self._run("aspirate", ops, lambda: parent(ops, use_channels, **kwargs))

    async def dispense(self, ops: list[Any], use_channels: list[int], **kwargs: Any) -> None:
        parent = super().dispense
        await self._run("dispense", ops, lambda: parent(ops, use_channels, **kwargs))

    def names(self) -> list[str]:
        return [name for name, _, _ in self.operations]
