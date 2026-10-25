"""A real embedded hub with mock devices, for the Inspector's browser tests and screenshots.

Every device runs on the mock driver or the firmware simulator. Nothing reaches hardware. The plant
waterer is the canonical demo device.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.discovery import DiscoveryResult, Unknown
from openhal.hub.hub import Hub
from openhal.kernel.principals import agent, human

PLANT_WATERER = """\
openhal: "0.1"
device: Plant waterer
id: plant-waterer
connect: { mock: plant-waterer, initial: { soil_moisture: 31, tank: ok } }
read:
  soil_moisture: { unit: percent, every: 5 s, range: [0, 100] }
  tank: { type: enum, values: [empty, ok], every: 2 s }
actions:
  water:
    description: Run the pump for a set time.
    args:
      duration: { unit: s, min: 1, max: 30 }
    require:
      - condition: "tank == ok"
        message: "pump can't run while tank is empty"
    max_runs: { count: 3, per: 1 h }
  stop:
    description: Stop the pump now.
safe_state:
  - action: stop
watchdog:
  heartbeat: 2 s
  on_loss: safe_state
hazard: low
notes: "An Arduino with a soil probe, a float switch in the tank and a 5 V pump."
provenance:
  source: hand-written
  by: sohan
  at: 2026-10-24
  verification: { status: unverified }
confirmed: { by: sohan, at: 2026-10-24 }
"""

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

DEVICE_FILES = {"plant-waterer": PLANT_WATERER, "curing-heater": CURING_HEATER, "bench-lamp": BENCH_LAMP}

SIMULATED_BOARD = Unknown(
    id="sim-bench-board",
    address="sim:bench-board",
    driver="openhal-firmware",
    identifiers={"firmware.product": "desk-fan", "firmware.version": "1.0.0"},
    label="Simulated OpenHAL firmware board",
)


@dataclass
class Harness:
    hub: Hub
    app: FastAPI
    human_token: str
    agent_token: str
    medium_token: str


def write_device_files(home: Path) -> None:
    devices = home / "devices"
    devices.mkdir(parents=True, exist_ok=True)
    for device_id, text in DEVICE_FILES.items():
        (devices / f"{device_id}.hal.yaml").write_text(text, encoding="utf-8")


async def start(home: Path) -> Harness:
    write_device_files(home)
    (home / "routines").mkdir(parents=True, exist_ok=True)
    hub = Hub(HubConfig(home=home), in_memory=True)
    await hub.start()
    hub.routines.create(human("sohan"), "water-when-dry", "yaml", WATER_WHEN_DRY)
    hub.routines.create(agent("bench-agent", "control_medium"), "cure-cycle", "yaml", CURE_CYCLE)
    hub.last_discovery = DiscoveryResult(unknown=[SIMULATED_BOARD])
    app = create_app(hub)
    human_token, _ = hub.tokens.create("sohan", "human")
    agent_token, _ = hub.tokens.create("bench-agent", "agent", "control_low")
    medium_token, _ = hub.tokens.create("lab-script", "agent", "control_medium")
    return Harness(hub, app, human_token, agent_token, medium_token)


def state(harness: Harness, port: int) -> dict[str, Any]:
    return {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "humanToken": harness.human_token,
        "agentToken": harness.agent_token,
        "mediumToken": harness.medium_token,
    }
