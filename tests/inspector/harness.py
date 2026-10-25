"""A real embedded hub with mock devices, for the Inspector's browser tests and screenshots.

Every device runs on the mock driver or the firmware simulator. Nothing reaches hardware.
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

DESK_FAN = """\
openhal: "0.1"
device: Desk fan controller
id: desk-fan
connect: { mock: desk-fan, simulate: desk-fan, initial: { fan_speed: 20 } }
read:
  temperature: { unit: degC, every: 1 s, range: [-20, 80] }
write:
  fan_speed: { unit: percent, min: 0, max: 100, step: 1, max_change_per_s: 20 }
actions:
  spin_test:
    description: Run the fan at full speed, then return to the set speed.
    args:
      seconds: { unit: s, min: 1, max: 30 }
    confirm: confirm
safe_state: { fan_speed: 0 }
watchdog:
  heartbeat: 2 s
  on_loss: safe_state
  max_duration:
    - when: "fan_speed > 80 %"
      for: 10 min
      then: { fan_speed: 50 }
hazard: low
notes: "Fan is next to the plant. It falls to 0 % if the hub stops sending heartbeats."
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
  purge:
    description: Blow the chamber clear with the heater off.
    confirm: confirm-each-time
    effects: [power]
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "desk-fan.fan_speed >= 30 %"
    message: "The heater needs the desk fan at 30 % or more."
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

KEEP_COOL = """\
id: keep-cool
description: Run the fan harder when the room is warm.
triggers:
  - every: 30 s
steps:
  - if: "desk-fan.temperature > 28 degC"
    then:
      - write: { device: desk-fan, channel: fan_speed, value: 60 % }
    else:
      - write: { device: desk-fan, channel: fan_speed, value: 20 % }
  - log: checked the fan
"""

CURE_CYCLE = """\
id: cure-cycle
description: Warm the resin for ten minutes with the fan running.
steps:
  - write: { device: desk-fan, channel: fan_speed, value: 40 % }
  - write: { device: curing-heater, channel: power, value: 30 W }
  - wait: 10 min
  - write: { device: curing-heater, channel: power, value: 0 W }
"""

DEVICE_FILES = {"desk-fan": DESK_FAN, "curing-heater": CURING_HEATER, "bench-lamp": BENCH_LAMP}

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
    log_mode: str


def write_device_files(home: Path) -> None:
    devices = home / "devices"
    devices.mkdir(parents=True, exist_ok=True)
    for device_id, text in DEVICE_FILES.items():
        (devices / f"{device_id}.hal.yaml").write_text(text, encoding="utf-8")


def mount_message_log(app: FastAPI, hub: Hub) -> str:
    routes = {getattr(route, "path", "") for route in app.routes}
    if "/rpc" in routes and "/v1/rpc/log" in routes:
        return "protocol"
    from tests.inspector.rpc_shim import mount

    mount(app, hub)
    return "fixture"


async def start(home: Path) -> Harness:
    write_device_files(home)
    (home / "routines").mkdir(parents=True, exist_ok=True)
    hub = Hub(HubConfig(home=home), in_memory=True)
    await hub.start()
    hub.routines.create(human("sohan"), "keep-cool", "yaml", KEEP_COOL)
    hub.routines.create(agent("bench-agent", "control_medium"), "cure-cycle", "yaml", CURE_CYCLE)
    hub.last_discovery = DiscoveryResult(unknown=[SIMULATED_BOARD])
    app = create_app(hub)
    log_mode = mount_message_log(app, hub)
    human_token, _ = hub.tokens.create("sohan", "human")
    agent_token, _ = hub.tokens.create("bench-agent", "agent", "control_low")
    medium_token, _ = hub.tokens.create("lab-script", "agent", "control_medium")
    return Harness(hub, app, human_token, agent_token, medium_token, log_mode)


def state(harness: Harness, port: int) -> dict[str, Any]:
    return {
        "url": f"http://127.0.0.1:{port}",
        "port": port,
        "humanToken": harness.human_token,
        "agentToken": harness.agent_token,
        "mediumToken": harness.medium_token,
        "log": harness.log_mode,
    }
