"""Generate the website's 30-second demo storyboard from the real CLI and MCP tools.

Every frame's text comes from running the command against an embedded hub with the `openhal init`
sample fan, which uses the mock driver. Run `uv run python -m tests.website.demo_steps` to rewrite
website/src/content/demo/steps.json. tests/website/test_demo_steps.py checks it stays current.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from openhal.client import AsyncClient
from openhal.mcp import Tools
from tests.website.shell import Session

ROOT = Path(__file__).resolve().parents[2]
STEPS_FILE = ROOT / "website" / "src" / "content" / "demo" / "steps.json"

STORY: list[dict[str, Any]] = [
    {
        "id": "confirm",
        "caption": "A person confirms the fan's limits. Agents never can.",
        "kind": "cli",
        "setup": ["openhal init"],
        "commands": ["openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml --by owner"],
    },
    {
        "id": "devices",
        "caption": "Start the hub and see what the fan allows.",
        "kind": "cli",
        "commands": ["openhald", "openhal devices demo-fan"],
    },
    {
        "id": "token",
        "caption": "Give Claude its own token, for low hazard devices only.",
        "kind": "cli",
        "commands": ["openhal token create --agent --scope control_low --name claude"],
    },
    {
        "id": "write",
        "caption": "Claude asks for 40 %. Every check passes, so the fan moves.",
        "kind": "mcp",
        "tool": "write",
        "args": {"device": "demo-fan", "channel": "fan_speed", "value": "40 %"},
    },
    {
        "id": "blocked",
        "caption": "Claude asks for 150 %. The kernel blocks it.",
        "kind": "mcp",
        "tool": "write",
        "args": {"device": "demo-fan", "channel": "fan_speed", "value": "150 %"},
    },
    {
        "id": "stop",
        "caption": "One stop puts every device in its safe state.",
        "kind": "cli",
        "commands": ['openhal stop --reason "demo over"'],
    },
]

TOKEN = re.compile(r"ohal_[A-Za-z0-9_-]{8,}")


def _mask_tokens(text: str) -> str:
    return TOKEN.sub("ohal_<agent token, shown once>", text)


async def _call(url: str, token: str, tool: str, args: dict[str, Any]) -> str:
    async with AsyncClient(url, token, use_human_token_file=False) as client:
        result = await getattr(Tools(client), tool)(**args)
    data = result.model_dump(mode="json", exclude_none=True)
    return json.dumps(data, indent=2, ensure_ascii=False)


def generate() -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="openhal-demo-") as tmp:
        session = Session(Path(tmp) / "home")
        agent_token = ""
        try:
            for step in STORY:
                frame = {"id": step["id"], "caption": step["caption"], "kind": step["kind"], "capture": ""}
                for command in step.get("setup", []):
                    if session.run(command).code != 0:
                        raise RuntimeError(f"{command} failed.")
                if step["kind"] == "cli":
                    parts = []
                    for command in step["commands"]:
                        result = session.run(command)
                        if result.code != 0:
                            raise RuntimeError(f"{command} exited {result.code}.\n{result.output}")
                        if command.startswith("openhal token create"):
                            agent_token = result.output.strip().splitlines()[-1]
                        output = _mask_tokens(result.output.rstrip())
                        parts.append(f"$ {command}" + (f"\n{output}" if output else ""))
                    frame["text"] = "\n\n".join(parts)
                else:
                    assert session.hub is not None
                    output = asyncio.run(_call(session.hub.url, agent_token, step["tool"], step["args"]))
                    call = json.dumps({"tool": step["tool"], "arguments": step["args"]}, indent=2, ensure_ascii=False)
                    frame["text"] = f"{call}\n\n{output}"
                frames.append(frame)
        finally:
            session.close()
    return frames


VOLATILE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}(T[0-9:.+Z-]+)?"), "<date>"),
    (re.compile(r'"value": -?\d+(\.\d+)?'), '"value": <n>'),
    (re.compile(r"\d+(\.\d+)?(?=\s+(degC|°C))"), "<n>"),
    (re.compile(r"\b[0-9a-f]{12,64}\b"), "<hex>"),
    (re.compile(r"\b\d+(\.\d+)?\s*s\b"), "<n> s"),
    (re.compile(r"\b(tok|id)_[A-Za-z0-9]+\b"), "<id>"),
    (re.compile(r"\b\d{9,}(\.\d+)?\b"), "<time>"),
]


def normalized(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Frames with values that change between runs (dates, readings, ids) masked."""
    out = []
    for frame in frames:
        text = frame["text"]
        for pattern, replacement in VOLATILE:
            text = pattern.sub(replacement, text)
        out.append({**frame, "text": text})
    return out


def render(frames: list[dict[str, Any]]) -> str:
    return json.dumps(frames, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    STEPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STEPS_FILE.write_text(render(generate()), encoding="utf-8")
    print(f"Wrote {STEPS_FILE.relative_to(ROOT)}")
