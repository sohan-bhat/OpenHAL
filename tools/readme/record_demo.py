"""Record the README demo from a real hub run, so the GIF shows real kernel decisions.

    uv run python tools/readme/record_demo.py

Uses the demo fan that `openhal init` installs (mock driver, simulated physics). A person confirms
its limits and sets it to 20 %, then an agent asks for 150 % and 60 %. The decisions, messages and
readings are written to docs/assets/demo-run.json, which tools/readme/demo_gif.py draws.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path

from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.kernel.commands import Write
from openhal.kernel.principals import agent, human
from openhal.spec.loader import from_data, parse_yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "demo-run.json"


def demo_file_text() -> str:
    from openhal.cli import init_cmd

    for name in dir(init_cmd):
        value = getattr(init_cmd, name)
        if isinstance(value, str) and "id: demo-fan" in value:
            return value
    raise SystemExit("Could not find the demo fan file in openhal.cli.init_cmd.")


async def main() -> None:
    data = parse_yaml(demo_file_text())
    draft = from_data(data)
    data["confirmed"] = {"by": "demo", "at": "2026-10-24", "sha256": draft.limits_sha256()}
    file = from_data(data)
    assert file.writable

    with tempfile.TemporaryDirectory() as home:
        hub = Hub(HubConfig(home=Path(home)), in_memory=True)
        hub.add_device(file)
        await hub.start(load_devices=False)
        person, claude = human("demo"), agent("claude", "control_low")
        await asyncio.sleep(1.2)
        setup = await hub.kernel.execute(Write(device="demo-fan", channel="fan_speed", value="20 %"), person)
        assert setup.status == "done", setup.message
        await asyncio.sleep(2.2)

        def reading(channel: str) -> float:
            sample = hub.kernel.devices["demo-fan"].latest(channel, hub.kernel.clock())
            assert sample is not None
            return round(float(sample.value), 1)

        before = {"fan_speed": reading("fan_speed"), "temperature": await read(hub, "temperature")}
        blocked = await hub.kernel.execute(Write(device="demo-fan", channel="fan_speed", value="150 %"), claude)
        granted = await hub.kernel.execute(Write(device="demo-fan", channel="fan_speed", value="60 %"), claude)
        after = []
        started = time.monotonic()
        for _ in range(4):
            await asyncio.sleep(1.0)
            after.append(
                {
                    "t": round(time.monotonic() - started, 1),
                    "fan_speed": await read(hub, "fan_speed"),
                    "temperature": await read(hub, "temperature"),
                }
            )
        await hub.close()

    run = {
        "device_file": {"id": file.device_id, "max": file.write["fan_speed"].max, "rate": 20, "unit": "%"},
        "before": before,
        "requests": [
            {
                "by": "claude (agent)",
                "value": "150 %",
                "status": blocked.status,
                "code": blocked.code,
                "message": blocked.message,
            },
            {
                "by": "claude (agent)",
                "value": "60 %",
                "status": granted.status,
                "code": granted.code,
                "message": granted.message,
            },
        ],
        "after": after,
    }
    OUT.write_text(json.dumps(run, indent=2) + "\n")
    print(json.dumps(run, indent=2))


async def read(hub: Hub, channel: str) -> float:
    value = (await hub.kernel.read("demo-fan", channel, human("demo"))).value
    return round(float(value), 1)  # type: ignore[arg-type]


if __name__ == "__main__":
    asyncio.run(main())
