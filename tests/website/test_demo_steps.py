"""The landing page storyboard must be what the real CLI and MCP tools print today.

Readings, dates and ids change from run to run, so they are masked before comparing. Everything
else, every message and every table, must match. Regenerate with
`uv run python -m tests.website.demo_steps` after a deliberate change to the CLI or the kernel.
"""

from __future__ import annotations

import json

from tests.website import demo_steps


def test_storyboard_matches_the_real_cli() -> None:
    saved = json.loads(demo_steps.STEPS_FILE.read_text(encoding="utf-8"))
    fresh = demo_steps.generate()
    assert demo_steps.normalized(fresh) == demo_steps.normalized(saved)


def test_every_frame_has_a_caption_and_text() -> None:
    saved = json.loads(demo_steps.STEPS_FILE.read_text(encoding="utf-8"))
    assert [frame["id"] for frame in saved] == [step["id"] for step in demo_steps.STORY]
    for frame in saved:
        assert frame["caption"].strip()
        assert frame["text"].strip()
        assert frame["kind"] in ("cli", "mcp")
        assert frame["capture"] == "" or frame["capture"].startswith("/captures/")
