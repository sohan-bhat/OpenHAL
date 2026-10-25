"""The real `openhal rpc` process. Lines in, lines out, only messages on stdout, closed when stdin closes."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from openhal.protocol.stdio import expects_answer, rpc_url
from tests.protocol.conftest import VERSION


def test_rpc_url_and_answer_counting() -> None:
    assert rpc_url("http://127.0.0.1:7420") == "ws://127.0.0.1:7420/rpc"
    assert rpc_url("https://hub.local/") == "wss://hub.local/rpc"
    assert rpc_url("ws://127.0.0.1:7420/rpc") == "ws://127.0.0.1:7420/rpc"
    assert expects_answer(b'{"jsonrpc": "2.0", "id": 1, "method": "hal/devices/list"}')
    assert not expects_answer(b'{"jsonrpc": "2.0", "method": "hal/initialized"}')
    assert expects_answer(b"{oops")
    assert expects_answer(b"[]")


async def test_openhal_rpc_bridges_stdio(base_url: str, tokens: dict[str, str], tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key not in ("OPENHAL_TOKEN", "OPENHAL_URL")}
    env |= {"OPENHAL_URL": base_url, "OPENHAL_HOME": str(tmp_path / "home")}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "openhal.cli.main",
        "rpc",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    assert process.stdin is not None
    lines = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "hal/initialize",
            "params": {
                "protocolVersion": VERSION,
                "clientInfo": {"name": "spawned", "version": "1"},
                "token": tokens["agent"],
            },
        },
        {"jsonrpc": "2.0", "method": "hal/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "hal/write",
            "params": {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"},
        },
    ]
    payload = "".join(json.dumps(line) + "\n" for line in lines) + "{broken\n"
    stdout, stderr = await asyncio.wait_for(process.communicate(payload.encode()), 60)
    assert process.returncode == 0, stderr.decode()
    messages = [json.loads(line) for line in stdout.decode().splitlines()]
    responses = {message.get("id"): message for message in messages if "method" not in message}
    assert responses[1]["result"]["principal"]["name"] == "claude"
    assert responses[2]["error"]["data"]["name"] == "LIMIT_EXCEEDED"
    assert responses[None]["error"]["data"]["name"] == "PARSE_ERROR"
    assert all(message["jsonrpc"] == "2.0" for message in messages)


async def test_openhal_rpc_reports_a_missing_hub_on_stderr(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "OPENHAL_TOKEN"}
    env |= {"OPENHAL_URL": "http://127.0.0.1:9", "OPENHAL_HOME": str(tmp_path / "home")}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "openhal.cli.main",
        "rpc",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(b""), 60)
    assert process.returncode == 3
    assert stdout == b""
    assert b"not running" in stderr
