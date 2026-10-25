"""The exact LIMIT_EXCEEDED trace from ADR 0015, with the canonical demo values.

desk-fan, fan_speed, current 20 %, requested 150 %, limit 100 % (max), granted 60 %.
"""

from __future__ import annotations

import json

from tests.kernel.conftest import FakeClock
from tests.protocol.conftest import VERSION, Connect

EXPECTED_ERROR = {
    "jsonrpc": "2.0",
    "id": 3,
    "error": {
        "code": -32010,
        "message": "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-11-02)",
        "data": {
            "name": "LIMIT_EXCEEDED",
            "kernelCode": "above_max",
            "kernelMessage": "Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.",
            "device": "desk-fan",
            "channel": "fan_speed",
            "requested": "150 %",
            "limit": {"max": "100 %"},
            "file": "desk-fan.hal.yaml",
            "confirmedBy": "sohan",
            "confirmedAt": "2026-11-02",
        },
    },
}


async def test_the_limit_exceeded_trace(transport: Connect, tokens: dict[str, str], clock: FakeClock) -> None:
    async with transport() as rpc:
        await rpc.send_text(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "hal/initialize",
                    "params": {
                        "protocolVersion": VERSION,
                        "clientInfo": {"name": "claude", "version": "1.0"},
                        "token": tokens["agent"],
                    },
                }
            )
        )
        assert (await rpc.response(1))["result"]["principal"]["kind"] == "agent"
        await rpc.notify("hal/initialized")
        await rpc.send_text(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "hal/read",
                    "params": {"device": "desk-fan", "channel": "fan_speed"},
                }
            )
        )
        current = (await rpc.response(2))["result"]
        assert (current["value"], current["unit"]) == (20.0, "percent")
        await rpc.send_text(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "hal/write",
                    "params": {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"},
                }
            )
        )
        assert await rpc.response(3) == EXPECTED_ERROR
        blocked = await rpc.note("hal/blocked", device="desk-fan")
        assert blocked["params"] == {
            "device": "desk-fan",
            "target": "write:fan_speed",
            "error": EXPECTED_ERROR["error"],
        }
        clock.advance(2)
        await rpc.send_text(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "hal/write",
                    "params": {"device": "desk-fan", "channel": "fan_speed", "value": "60 %"},
                }
            )
        )
        assert await rpc.response(4) == {
            "jsonrpc": "2.0",
            "id": 4,
            "result": {
                "status": "done",
                "device": "desk-fan",
                "channel": "fan_speed",
                "value": 60.0,
                "unit": "percent",
            },
        }
