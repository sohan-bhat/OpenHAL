"""The GPIO stop button config.yaml names (docs/SAFETY.md, stop_all).

A press stops everything. A button the person configured but the hub can't watch stops the hub
from starting, before any device connects.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal.hub.config import GpioStopSettings, HubConfig
from openhal.hub.hub import Hub

gpiozero = pytest.importorskip("gpiozero")
from gpiozero.pins.mock import MockFactory  # noqa: E402


@pytest.fixture
def pins() -> Iterator[MockFactory]:
    previous = gpiozero.Device.pin_factory
    factory = MockFactory()
    gpiozero.Device.pin_factory = factory
    yield factory
    factory.reset()
    gpiozero.Device.pin_factory = previous


async def test_a_press_stops_everything(tmp_path: Path, pins: MockFactory) -> None:
    hub = Hub(HubConfig(home=tmp_path, stop_button=GpioStopSettings(pin=27)), in_memory=True)
    await hub.start()
    try:
        assert not hub.kernel.stopped
        pins.pin(27).drive_low()
        for _ in range(100):
            if hub.kernel.stopped:
                break
            await asyncio.sleep(0.01)
        assert hub.kernel.stopped
        assert hub.kernel.stop_reason == "the GPIO stop button was pressed"
        assert hub.audit.entries(event="stop_button", limit=1)[0].status == "done"
    finally:
        await hub.close()


async def test_a_button_the_hub_cannot_watch_stops_the_start(tmp_path: Path, pins: MockFactory) -> None:
    hub = Hub(HubConfig(home=tmp_path, stop_button=GpioStopSettings(pin=40)), in_memory=True)
    with pytest.raises(RuntimeError, match=r"sets stop_button\.pin 40, but the hub can.t watch it"):
        await hub.start()
    assert hub.audit.entries(event="stop_button", limit=1)[0].status == "failed"
    assert hub.started_at is None
    await hub.close()


async def test_no_button_configured_watches_nothing(tmp_path: Path) -> None:
    hub = Hub(HubConfig(home=tmp_path), in_memory=True)
    await hub.start()
    try:
        assert hub.audit.entries(event="stop_button", limit=1) == []
    finally:
        await hub.close()
