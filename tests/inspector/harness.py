"""A real embedded hub with mock devices, for the Inspector's browser tests and screenshots.

Every device runs on the mock driver or a firmware simulator. Nothing reaches hardware. The plant
waterer is the canonical demo device, examples/plant-waterer/mock/plant-waterer.hal.yaml on the
simulated board behind `sim:plant-waterer`. The harness adds two routes for tests, under /_harness,
that refill and drain its tank. The last discovery holds one unknown board for the driver writer, a
herb waterer at `sim:herb-waterer` that runs the plant waterer's firmware under its own product name,
so no library file matches it and the writer screens stay on the canonical example.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from openhal.demo.scenario import example_file
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, PlantWatererSimulator
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.discovery import DiscoveryResult, Unknown
from openhal.hub.hub import Hub
from openhal.kernel.principals import agent, human

CURING_HEATER = """\
openhal: "0.1"
device: Resin curing heater
id: curing-heater
connect: { mock: curing-heater, simulate: heater }
read:
  temperature: { unit: degC, every: 1 s, range: [0, 90] }
write:
  power: { unit: W, min: 0, max: 60, max_change_per_s: 10 }
actions:
  vent:
    description: Open the chamber vent for a few seconds.
    args:
      seconds: { unit: s, min: 1, max: 20 }
    confirm: confirm-each-time
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "temperature < 70 degC"
    message: "The heater adds no power above 70 degC."
watchdog:
  heartbeat: 2 s
  on_loss: safe_state
  max_duration:
    - when: "power > 40 W"
      for: 15 min
hazard: medium
provenance:
  source: hand-written
  by: sohan
  at: 2026-10-24
  verification: { status: tested-reads }
confirmed: { by: sohan, at: 2026-10-24 }
"""

BENCH_LAMP = """\
openhal: "0.1"
device: Bench lamp
id: bench-lamp
connect: { mock: bench-lamp }
write:
  brightness: { unit: percent, min: 0, max: 80, suggested: true }
  enabled: { type: bool }
safe_state: { enabled: false }
hazard: low
provenance:
  source: manual
  by: openhal writer
  at: 2026-10-24
"""

WATER_WHEN_DRY = """\
id: water-when-dry
description: Water the plant when the soil is dry.
triggers:
  - every: 30 min
steps:
  - if: "plant-waterer.soil_moisture < 30 %"
    then:
      - action: { device: plant-waterer, action: water, args: { duration: 20 s } }
  - log: checked the soil
"""

CURE_CYCLE = """\
id: cure-cycle
description: Warm the resin for ten minutes.
steps:
  - write: { device: curing-heater, channel: power, value: 30 W }
  - wait: 10 min
  - write: { device: curing-heater, channel: power, value: 0 W }
"""

DEVICE_FILES = {"curing-heater": CURING_HEATER, "bench-lamp": BENCH_LAMP}
SPEED = 20.0

UNKNOWN_PRODUCT = "herb-waterer"

SIMULATED_BOARD = Unknown(
    id=f"sim-{UNKNOWN_PRODUCT}",
    address=f"sim:{UNKNOWN_PRODUCT}",
    driver="openhal-firmware",
    identifiers={"firmware.product": UNKNOWN_PRODUCT, "firmware.version": "1.0.0"},
    label="Simulated OpenHAL firmware board",
)


@dataclass
class Harness:
    hub: Hub
    app: FastAPI
    human_token: str
    agent_token: str
    medium_token: str
    board: PlantWatererSimulator


def write_device_files(home: Path) -> None:
    devices = home / "devices"
    devices.mkdir(parents=True, exist_ok=True)
    for device_id, text in DEVICE_FILES.items():
        (devices / f"{device_id}.hal.yaml").write_text(text, encoding="utf-8")
    waterer = example_file()
    (devices / waterer.name).write_text(waterer.read_text(encoding="utf-8"), encoding="utf-8")


def mount_board(app: FastAPI, board: PlantWatererSimulator) -> None:
    @app.post("/_harness/plant-waterer/refill", include_in_schema=False)
    async def refill() -> dict[str, bool]:
        board.refill()
        return {"tank_ok": board.tank_ok}

    @app.post("/_harness/plant-waterer/drain", include_in_schema=False)
    async def drain() -> dict[str, bool]:
        board.drain()
        return {"tank_ok": board.tank_ok}


async def start(home: Path) -> Harness:
    write_device_files(home)
    (home / "routines").mkdir(parents=True, exist_ok=True)
    board = PlantWatererSimulator(speed=SPEED)
    SIMULATORS["plant-waterer"] = board
    SIMULATORS[UNKNOWN_PRODUCT] = PlantWatererSimulator(product=UNKNOWN_PRODUCT, speed=SPEED)
    hub = Hub(HubConfig(home=home), in_memory=True)
    await hub.start()
    hub.routines.create(human("sohan"), "water-when-dry", "yaml", WATER_WHEN_DRY)
    hub.routines.create(agent("bench-agent", "control_medium"), "cure-cycle", "yaml", CURE_CYCLE)
    hub.last_discovery = DiscoveryResult(unknown=[SIMULATED_BOARD])
    app = create_app(hub)
    mount_board(app, board)
    human_token, _ = hub.tokens.create("sohan", "human")
    agent_token, _ = hub.tokens.create("bench-agent", "agent", "control_low")
    medium_token, _ = hub.tokens.create("lab-script", "agent", "control_medium")
    return Harness(hub, app, human_token, agent_token, medium_token, board)


def state(harness: Harness, port: int) -> dict[str, Any]:
    return {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "humanToken": harness.human_token,
        "agentToken": harness.agent_token,
        "mediumToken": harness.medium_token,
    }
