"""Helpers shared by the driver tests. Every change goes through a real kernel, never around it."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from openhal.drivers.base import Driver, Reading
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Decision, Write
from openhal.kernel.principals import human
from openhal.spec.models import DeviceFile

WHO = human("tester")


class Bench:
    """A kernel with one registered device, and short ways to drive it."""

    def __init__(self, file: DeviceFile, driver: Driver) -> None:
        self.file = file
        self.driver = driver
        self.kernel = Kernel()
        self.kernel.register(file, driver)

    @property
    def device(self) -> str:
        return self.file.device_id

    async def connect(self) -> Bench:
        await self.kernel.connect(self.device)
        return self

    async def read(self, channel: str) -> Reading:
        return await self.kernel.read(self.device, channel, WHO)

    async def write(self, channel: str, value: Any) -> Decision:
        return await self.kernel.execute(Write(device=self.device, channel=channel, value=value), WHO)

    async def act(self, action: str, **args: Any) -> Decision:
        return await self.kernel.execute(Action(device=self.device, action=action, args=args), WHO)

    async def stop(self) -> str:
        report = await self.kernel.stop_all(WHO, "test")
        self.kernel.unlock(WHO, "unlock")
        return report.devices[0].status

    async def close(self) -> None:
        await self.driver.close()
        self.kernel.audit.close()


async def eventually(check: Callable[[], Awaitable[bool]], within: float = 2.0) -> None:
    """Wait until an async check passes."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + within
    while not await check():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


def assert_done(decision: Decision) -> None:
    assert decision.status == "done", f"{decision.status} {decision.code}: {decision.message}"


def assert_failed(decision: Decision, text: str) -> None:
    assert decision.status == "failed", f"{decision.status} {decision.code}: {decision.message}"
    assert text in decision.message, decision.message
