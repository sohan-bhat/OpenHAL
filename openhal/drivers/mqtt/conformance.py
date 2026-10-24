"""The mqtt driver's conformance case, against the in-process broker and the simulated fan."""

from __future__ import annotations

import asyncio
import time

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.mqtt.driver import MqttDriver
from openhal.drivers.mqtt.simulator import MqttBroker, SimulatedFan
from openhal.spec import loads
from openhal.spec.models import DeviceFile

CHANNELS = """
read:
  temperature: { unit: degC, stream: true, map: { state: lab/fan/sensor, format: json, json: climate.temperature } }
  humidity: { unit: percent, stream: true, map: { state: lab/fan/sensor, format: json, json: climate.humidity } }
write:
  speed: { unit: percent, min: 0, max: 100, map: { state: lab/fan/speed, command: lab/fan/speed/set } }
  power: { type: bool, map: { state: lab/fan/power, command: lab/fan/power/set } }
  mode:
    type: enum
    values: [auto, eco, boost]
    map: { state: lab/fan/mode, command: lab/fan/mode/set, format: json, json: mode }
safe_state: { power: false, speed: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(broker: MqttBroker, *, extra: str = "", timeout: str = "2 s") -> DeviceFile:
    connect = f"{{ mqtt: 127.0.0.1, port: {broker.port}, timeout: {timeout}{extra} }}"
    return loads(f"device: Conformance MQTT fan\nid: conformance-mqtt\nconnect: {connect}\n{CHANNELS}")


async def wait_until(condition: object, within: float = 3.0) -> None:
    """Poll a callable until it returns true, for state that arrives on paho's thread."""
    assert callable(condition)
    deadline = time.monotonic() + within
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition did not become true in time")
        await asyncio.sleep(0.02)


class _Case:
    def __init__(self) -> None:
        self.broker = MqttBroker().start()
        self.fan = SimulatedFan(self.broker).attach()
        self.file = device_file(self.broker)

    def make(self, file: DeviceFile) -> Driver:
        return MqttDriver(file)

    async def break_connection(self, driver: Driver) -> None:
        assert isinstance(driver, MqttDriver)
        self.broker.kick_all()
        await wait_until(lambda: not driver.connected)

    async def make_slow(self, driver: Driver) -> None:
        self.broker.paused = True

    async def cleanup(self) -> None:
        self.broker.paused = False
        self.broker.stop()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(
        name="mqtt",
        file=state.file,
        make=state.make,
        break_connection=state.break_connection,
        make_slow=state.make_slow,
        cleanup=state.cleanup,
    )
