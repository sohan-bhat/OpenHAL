"""The Inspector's test hub with the print babysitter, for the browser tests and the website's captures.

    PYTHONPATH=. uv run python dashboard/e2e/print_hub.py --port 7431 --state STATE.json
    PYTHONPATH=. uv run python dashboard/e2e/print_hub.py --port 7420 --state STATE.json --only-print

Run it from the repository root. It is the hub of tests/inspector/harness.py with the two devices
of examples/print-babysitter/ added. `printer` is a Klipper printer on the Moonraker simulator a few
minutes into a print, and `printer-cam` is its webcam on the simulated crowsnest snapshot server,
showing the demo's line drawings. Both are reached through httpx.MockTransport, so nothing opens a
socket to a printer or a camera. `--only-print` leaves out the plant waterer and the mock devices,
for the website's captures.

The state file adds `printToken`, an agent token named print-watcher with the control_medium scope
that the printer's medium hazard needs. Three routes help tests.

- `POST /_harness/printer-cam/show/{frame}` changes the camera's frame, first-layer or come-loose.
- `POST /_harness/printer/print` starts the simulated print again, so a cancel can run more than once.
- `POST /_harness/printer/error` puts the printer in Klipper's error state, which its interlock checks.

Stop it with its PID.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException

from openhal.demo.scenario import CAMERA, DEVICE, FILES, FOLDER, FRAMES, SimulatedPrinter, example, frame, printing
from openhal.demo.webcam import SimulatedWebcam, Webcam
from openhal.drivers.moonraker.simulator import MoonrakerSim
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import load
from tests.inspector.harness import start, state

PRINT_AGENT = "print-watcher"


@dataclass
class PrintHub:
    hub: Hub
    app: FastAPI
    tokens: dict[str, str]
    sim: MoonrakerSim
    webcam: Webcam


async def add_print_babysitter(hub: Hub) -> tuple[MoonrakerSim, Webcam]:
    """Add the printer and its camera on their simulators to a hub that is already running."""
    sim = printing()
    webcam = Webcam({name: frame(name) for name in FRAMES}, FRAMES[0])
    paths = {device: example(FOLDER, name) for device, name in FILES.items()}
    printer, camera = load(paths[DEVICE]), load(paths[CAMERA])
    await hub.add_and_start(printer, driver=SimulatedPrinter(printer, sim), path=paths[DEVICE])
    await hub.add_and_start(camera, driver=SimulatedWebcam(camera, webcam), path=paths[CAMERA])
    return sim, webcam


def mount_print_routes(app: FastAPI, sim: MoonrakerSim, webcam: Webcam) -> None:
    @app.post("/_harness/printer-cam/show/{name}", include_in_schema=False)
    async def show(name: str) -> dict[str, str]:
        if name not in webcam.frames:
            raise HTTPException(404, f"The webcam has no frame named {name}.")
        webcam.show(name)
        return {"showing": webcam.showing}

    @app.post("/_harness/printer/print", include_in_schema=False)
    async def print_again() -> dict[str, Any]:
        sim.state.objects.update(copy.deepcopy(printing().state.objects))
        return {"state": sim.state.objects["print_stats"]["state"]}

    @app.post("/_harness/printer/error", include_in_schema=False)
    async def fail() -> dict[str, Any]:
        sim.state.objects["print_stats"]["state"] = "error"
        return {"state": "error"}


async def only_print(home: Path) -> PrintHub:
    (home / "routines").mkdir(parents=True, exist_ok=True)
    hub = Hub(HubConfig(home=home), in_memory=True)
    await hub.start(load_devices=False)
    sim, webcam = await add_print_babysitter(hub)
    app = create_app(hub)
    mount_print_routes(app, sim, webcam)
    human_token, _ = hub.tokens.create("owner", "human")
    agent_token, _ = hub.tokens.create("bench-agent", "agent", "control_low")
    medium_token, _ = hub.tokens.create("lab-script", "agent", "control_medium")
    print_token, _ = hub.tokens.create(PRINT_AGENT, "agent", "control_medium")
    tokens = {"humanToken": human_token, "agentToken": agent_token, "mediumToken": medium_token}
    return PrintHub(hub, app, {**tokens, "printToken": print_token}, sim, webcam)


async def with_harness(home: Path) -> PrintHub:
    harness = await start(home)
    sim, webcam = await add_print_babysitter(harness.hub)
    mount_print_routes(harness.app, sim, webcam)
    print_token, _ = harness.hub.tokens.create(PRINT_AGENT, "agent", "control_medium")
    tokens = {key: value for key, value in state(harness, 0).items() if key.endswith("Token")}
    return PrintHub(harness.hub, harness.app, {**tokens, "printToken": print_token}, sim, webcam)


def write_state(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def main(port: int, state_path: Path, home: Path | None, print_only: bool) -> None:
    folder = home or Path(tempfile.mkdtemp(prefix="openhal-inspector-"))
    served = await (only_print(folder) if print_only else with_harness(folder))
    server = uvicorn.Server(uvicorn.Config(served.app, host="127.0.0.1", port=port, log_level="warning"))
    described = {"url": f"http://127.0.0.1:{port}", "port": port, **served.tokens}
    await asyncio.to_thread(write_state, state_path, json.dumps(described, indent=2))
    try:
        await server.serve()
    finally:
        await served.hub.close()


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=7431)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--only-print", action="store_true", help="Run only the printer and its camera.")
    args = parser.parse_args()
    if args.port == 4000:
        parser.error("Port 4000 is reserved. Choose another port.")
    asyncio.run(main(args.port, args.state, args.home, args.only_print))


if __name__ == "__main__":
    run()
