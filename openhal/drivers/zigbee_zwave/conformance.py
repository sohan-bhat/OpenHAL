"""The zigbee-zwave driver's conformance cases. The registry runs the Zigbee2MQTT one, and the driver
tests run both, the Z-Wave one against a zwave-js-server simulator in the test's event loop."""

from __future__ import annotations

import asyncio
import time

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.mqtt.simulator import MqttBroker
from openhal.drivers.zigbee_zwave.driver import ZigbeeZWaveDriver
from openhal.drivers.zigbee_zwave.simulator import Zigbee2MqttSim, ZWaveJsSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

LAMP = """
read:
  linkquality: { unit: dimensionless }
write:
  brightness: { unit: percent, min: 0, max: 100, map: { scale: 0.39370078740157477 } }
  state: { type: bool }
  power_on_behavior: { type: enum, values: ["off", "on", "previous"] }
safe_state: { state: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""

DIMMER = """
write:
  level: { unit: percent, min: 0, max: 99, map: { command_class: 38, property: currentValue } }
safe_state: { level: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def zigbee_file(
    broker: MqttBroker, *, name: str = "desk_lamp", channels: str = LAMP, extra: str = "", timeout: str = "2 s"
) -> DeviceFile:
    connect = f'{{ zigbee-zwave: "mqtt://127.0.0.1:{broker.port}", friendly_name: {name}, timeout: {timeout}{extra} }}'
    return loads(f"device: Conformance lamp\nid: conformance-zigbee\nconnect: {connect}\n{channels}")


def zwave_file(
    sim: ZWaveJsSim, *, node: int = 3, channels: str = DIMMER, extra: str = "", timeout: str = "1 s"
) -> DeviceFile:
    connect = f'{{ zigbee-zwave: "{sim.url}", node: {node}, timeout: {timeout}{extra} }}'
    return loads(f"device: Conformance dimmer\nid: conformance-zwave\nconnect: {connect}\n{channels}")


async def wait_disconnected(driver: Driver) -> None:
    deadline = time.monotonic() + 3.0
    while (await driver.health()).connected:
        if time.monotonic() > deadline:
            raise AssertionError("the driver did not notice the bridge going away")
        await asyncio.sleep(0.02)


def case() -> ConformanceCase:
    broker = MqttBroker().start()
    Zigbee2MqttSim(broker).attach()

    async def broken(driver: Driver) -> None:
        broker.kick_all()
        await wait_disconnected(driver)

    async def cleanup() -> None:
        broker.stop()

    return ConformanceCase(
        name="zigbee-zwave",
        file=zigbee_file(broker),
        make=ZigbeeZWaveDriver,
        break_connection=broken,
        cleanup=cleanup,
    )


def zwave_case(sim: ZWaveJsSim) -> ConformanceCase:
    """The Z-Wave case against a started simulator. The caller closes the simulator."""

    async def broken(driver: Driver) -> None:
        await sim.drop()
        await wait_disconnected(driver)

    async def slow(driver: Driver) -> None:
        sim.latency_s = 3.0

    async def cleanup() -> None:
        sim.latency_s = 0.0

    return ConformanceCase(
        name="zigbee-zwave (zwave-js)",
        file=zwave_file(sim),
        make=ZigbeeZWaveDriver,
        break_connection=broken,
        make_slow=slow,
        cleanup=cleanup,
    )
