"""The matter driver's conformance case, against a simulated Matter Server running in its own thread."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.matter.driver import MatterDriver
from openhal.drivers.matter.simulator import MatterServerSim
from openhal.spec import loads
from openhal.spec.models import DeviceFile

BULB = """
read:
  identify_time: { unit: s, map: { path: 1/3/0 } }
write:
  level:
    unit: percent
    min: 0
    max: 100
    map:
      path: 1/8/0
      scale: 0.39370078740157477
      command: MoveToLevelWithOnOff
      payload: { level: "{value}", transitionTime: 0, optionsMask: 0, optionsOverride: 0 }
  power: { type: bool, map: { path: 1/6/0, on_command: On, off_command: Off } }
actions:
  identify:
    args: { seconds: { unit: s, min: 1, max: 30 } }
    map: { endpoint: 1, cluster: 3, command: Identify, payload: { identifyTime: "{seconds}" } }
safe_state: { power: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""


def device_file(url: str, *, node: int = 5, channels: str = BULB, timeout: str = "2 s") -> DeviceFile:
    connect = f'{{ matter: "{url}", node: {node}, timeout: {timeout} }}'
    return loads(f"device: Conformance bulb\nid: conformance-matter\nconnect: {connect}\n{channels}")


class ThreadedServer:
    """The simulator on its own event loop, so a synchronous caller can start it."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.sim = MatterServerSim()
        started: Future[None] = Future()

        def run() -> None:
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.sim.start())
            started.set_result(None)
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, name="openhal-matter-sim", daemon=True)
        self.thread.start()
        started.result(timeout=5)

    async def run(self, coroutine: object) -> None:
        """Run a simulator coroutine from another event loop without blocking it."""
        assert asyncio.iscoroutine(coroutine)
        await asyncio.wait_for(asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coroutine, self.loop)), 5)

    async def stop(self) -> None:
        await self.run(self.sim.close())
        self.loop.call_soon_threadsafe(self.loop.stop)
        await asyncio.to_thread(self.thread.join, 5)


def case() -> ConformanceCase:
    server = ThreadedServer()

    async def broken(driver: Driver) -> None:
        await server.run(server.sim.drop())
        deadline = time.monotonic() + 3.0
        while (await driver.health()).connected:
            if time.monotonic() > deadline:
                raise AssertionError("the driver did not detect the server going away")
            await asyncio.sleep(0.02)

    async def cleanup() -> None:
        await server.stop()

    return ConformanceCase(
        name="matter", file=device_file(server.sim.url), make=MatterDriver, break_connection=broken, cleanup=cleanup
    )
