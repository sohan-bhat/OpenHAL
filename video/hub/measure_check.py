"""Measure the time the hub adds to check a request, on the demo's simulated arm (video/data/STATS.md).

    .venv/bin/python video/hub/measure_check.py --cache video/assets/menagerie --scratch <folder> --count 1200

The run serves a real hub on a free loopback port from a fresh home in the scratch folder, with only
the simulated SO-101 from so101-demo.hal.yaml, and sends it requests one at a time over HTTP with an
agent token, as `openhal mcp` does. Three clocks run inside the hub process.

- added, from the moment the request reaches the hub's HTTP app to the moment the driver receives the
  command. That covers parsing, the token, the request model, the safety kernel, the device lock and
  the grant, everything the hub does before the device sees the command.
- kernel, from the kernel's execute call to the moment the driver receives the command.
- blocked, from the moment a request the kernel blocks reaches the app to the moment its response starts.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import socket
import statistics
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import menagerie
import uvicorn
from record import confirmed, expect

from openhal import __version__
from openhal.client import AsyncClient
from openhal.demo import rig
from openhal.drivers.openhal_firmware.driver import PORTS_ENV
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub

HERE = Path(__file__).resolve().parent
ARM_FILE = HERE / "so101-demo.hal.yaml"
FORBIDDEN_PORTS = frozenset({4000, 7420})
ARRIVED: ContextVar[int] = ContextVar("arrived", default=0)
ENTERED: ContextVar[int] = ContextVar("entered", default=0)
FAST = {axis: {"value": value, "unit": "mm"} for axis, value in (("x", 200), ("y", 0), ("z", 40))}
FAST["speed"] = {"value": 120, "unit": "deg/s"}


class Timings:
    def __init__(self) -> None:
        self.added: list[float] = []
        self.kernel: list[float] = []
        self.blocked: list[float] = []
        self.round_trip: dict[str, list[float]] = {"write": [], "blocked": []}
        self.on = False

    def app(self, inner: Any) -> Callable[[Any, Any, Any], Awaitable[None]]:
        async def timed(scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await inner(scope, receive, send)
                return
            arrived = time.perf_counter_ns()
            ARRIVED.set(arrived)

            async def sending(message: Any) -> None:
                if message["type"] == "http.response.start" and self.on and scope["path"] == "/v1/action":
                    self.blocked.append((time.perf_counter_ns() - arrived) / 1e6)
                await send(message)

            await inner(scope, receive, sending)

        return timed


def hook(hub: Hub, timings: Timings) -> None:
    """Stamp the kernel's entry and the driver's receipt of each write."""
    kernel = hub.kernel
    execute = kernel.execute
    driver = kernel.devices["arm"].driver
    write = driver._write  # noqa: SLF001

    async def entering(*args: Any, **kwargs: Any) -> Any:
        ENTERED.set(time.perf_counter_ns())
        return await execute(*args, **kwargs)

    async def receiving(channel: str, value: Any) -> Any:
        now = time.perf_counter_ns()
        if timings.on:
            timings.added.append((now - ARRIVED.get()) / 1e6)
            timings.kernel.append((now - ENTERED.get()) / 1e6)
        return await write(channel, value)

    kernel.execute = entering  # type: ignore[method-assign]
    driver._write = receiving  # type: ignore[method-assign]  # noqa: SLF001


@contextlib.asynccontextmanager
async def serving(hub: Hub, timings: Timings) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    expect(port not in FORBIDDEN_PORTS, f"the hub came up on port {port}")
    config = uvicorn.Config(timings.app(create_app(hub)), log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        while not server.started:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task
        listener.close()


def summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    cut = statistics.quantiles(ordered, n=100)
    return {
        "count": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p10_ms": round(cut[9], 3),
        "p90_ms": round(cut[89], 3),
        "p99_ms": round(cut[98], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
    }


async def measure(cache: Path, home: Path, count: int, warm_up: int) -> dict[str, Any]:
    os.environ.pop(PORTS_ENV, None)
    os.environ["OPENHAL_SO101_SCENE"] = str(menagerie.scene(cache))
    person = rig.set_up_home(home, "owner")
    text, _file = confirmed(ARM_FILE.read_text(encoding="utf-8"), "owner")
    (home / "devices" / "arm.hal.yaml").write_text(text, encoding="utf-8")
    hub = Hub(HubConfig(home=home))
    timings = Timings()
    try:
        await hub.start()
        expect(set(hub.kernel.devices) == {"arm"} and hub.kernel.devices["arm"].driver.simulated, "not the sim arm")
        hook(hub, timings)
        async with serving(hub, timings) as url, AsyncClient(url, person, use_human_token_file=False) as owner:
            token = (await owner.create_token("measure", kind="agent", scope="control_medium")).token
            async with AsyncClient(url, token, use_human_token_file=False) as agent:
                for number in range(warm_up + count):
                    timings.on = number >= warm_up
                    began = time.perf_counter_ns()
                    decision = await agent.write("arm", "gripper_goal", 50.0 + 0.02 * (number % 2), "%")
                    if timings.on:
                        timings.round_trip["write"].append((time.perf_counter_ns() - began) / 1e6)
                    expect(decision.status == "done", f"write {number} came back {decision.status}: {decision.message}")
                for number in range(warm_up + count):
                    timings.on = number >= warm_up
                    began = time.perf_counter_ns()
                    decision = await agent.action("arm", "move_to", FAST)
                    if timings.on:
                        timings.round_trip["blocked"].append((time.perf_counter_ns() - began) / 1e6)
                    expect(decision.code == "above_max", f"the fast move came back {decision.status} {decision.code}")
                timings.on = False
    finally:
        await hub.close()
    return {
        "measured_on": time.strftime("%Y-%m-%d %H:%M"),
        "openhal": __version__,
        "python": sys.version.split()[0],
        "requests_per_kind": count,
        "warm_up_per_kind": warm_up,
        "added_before_the_driver": summary(timings.added),
        "kernel_before_the_driver": summary(timings.kernel),
        "blocked_until_the_response": summary(timings.blocked),
        "client_round_trip_write": summary(timings.round_trip["write"]),
        "client_round_trip_blocked": summary(timings.round_trip["blocked"]),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Measure the hub's check time on the simulated arm.")
    parser.add_argument("--cache", type=Path, required=True, help="A folder for the Menagerie model.")
    parser.add_argument("--scratch", type=Path, required=True, help="A scratch folder for the temporary home.")
    parser.add_argument("--count", type=int, default=1200, help="Measured requests of each kind.")
    parser.add_argument("--warm-up", type=int, default=50, help="Requests of each kind sent first and not counted.")
    parser.add_argument("--out", type=Path, help="Write the result as JSON here too.")
    options = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="openhal-measure-", dir=options.scratch) as folder:
        result = asyncio.run(measure(options.cache, Path(folder), options.count, options.warm_up))
    text = json.dumps(result, indent=2)
    print(text)
    if options.out:
        options.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
