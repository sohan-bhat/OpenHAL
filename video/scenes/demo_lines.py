"""Turn a recorded take into the blocks Claude Code's terminal shows, for the demo's edit.

Each block quotes a line from the take's Claude Code stream. A tool call reads the way Claude Code
prints an MCP call, server - tool (MCP)(key: value), and a long call or result is shortened with an
ellipsis the way Claude Code shortens one. Status words in a result take the site's status colors.
"""

from __future__ import annotations

import json
import re

from demo_take import Line, Take

FPS = 30
CPS = 30
ARGS_MAX = 150
RESULT_MAX = 120
STATUS_TONES = {
    "done": "ok",
    "granted": "ok",
    "approved": "ok",
    "pending": "pending",
    "blocked": "blocked",
    "cancelled": "blocked",
    "stopped": "blocked",
}
OMIT = ["The red cube is picked up and held over its starting spot."]
"""Claude's closing message of the first turn, left out of the terminal's history.

Claude wrote the message after a check made before the Approve click, so beside the drop the
video has just shown the message would read as the current state.
"""


def find(
    take: Take, kind: str, after: float = 0.0, tool: str | None = None, starts: str | None = None, nth: int = 0
) -> Line:
    """The nth line of a kind after a take time, matched by tool name or text start."""
    found = [
        line
        for line in take.lines
        if line.kind == kind
        and line.t >= after
        and (tool is None or line.tool == f"mcp__openhal__{tool}")
        and (starts is None or line.text.startswith(starts))
    ]
    if len(found) <= nth:
        raise SystemExit(f"{take.name}: no {kind} {tool or starts or ''} after {after:.2f} s")
    return found[nth]


def result_of(take: Take, call: Line) -> Line:
    """The result line of a tool call."""
    for line in take.lines:
        if line.kind == "result" and line.tool_id == call.tool_id:
            return line
    raise SystemExit(f"{take.name}: no result for {call.tool}")


def audit(take: Take, event: str, after: float = 0.0, target: str | None = None, status: str | None = None) -> dict:
    """The first audit entry of an event after a take time."""
    for entry in take.audit:
        if (
            entry["event"] == event
            and entry["t"] >= after
            and (target is None or entry.get("target") == target)
            and (status is None or entry.get("status") == status)
        ):
            return entry
    raise SystemExit(f"{take.name}: no audit {event} {target or ''} after {after:.2f} s")


def cut(text: str, limit: int) -> str:
    """Claude Code's own shortening of a long line, the start and an ellipsis."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def call_args(args: dict) -> str:
    """A tool call's input as Claude Code prints it, key: JSON value, joined by commas."""
    return ", ".join(
        f"{key}: {json.dumps(value, separators=(',', ':'), ensure_ascii=False)}" for key, value in args.items()
    )


def result_spans(text: str, limit: int = RESULT_MAX) -> list[dict]:
    """A result's text, shortened, with each status word set in its status color."""
    shown = cut(text, limit)
    spans: list[dict] = []
    pos = 0
    for match in re.finditer(r'"status":"(\w+)"|LIMIT_EXCEEDED|"code":"(\w+)"', shown):
        word = match.group(1)
        if match.group(0) == "LIMIT_EXCEEDED":
            start, end, tone = match.start(), match.end(), "blocked"
        elif word in STATUS_TONES:
            start, end, tone = match.start(1), match.end(1), STATUS_TONES[word]
        else:
            continue
        spans.append({"text": shown[pos:start], "tone": "muted"})
        spans.append({"text": shown[start:end], "tone": tone, "bold": True})
        pos = end
    spans.append({"text": shown[pos:], "tone": "muted"})
    return [span for span in spans if span["text"]]


def tool_block(
    call: Line,
    at: int,
    result: Line | None = None,
    result_at: int | None = None,
    brand: bool = False,
    limit: int = RESULT_MAX,
) -> dict:
    """A tool call block, with its result when the scene shows it."""
    block = {
        "kind": "tool",
        "server": "openhal",
        "tool": call.tool.removeprefix("mcp__openhal__"),
        "args": cut(call_args(call.args), ARGS_MAX),
        "at": at,
        "brand": brand,
    }
    if result is not None and result_at is not None:
        block["result"] = {"spans": result_spans(result.result, limit), "at": result_at}
    return block


def text_block(line: Line, at: int) -> dict:
    """An assistant message shown whole."""
    return {"kind": "text", "text": line.text, "at": at}


def spinner(at: int, until: int, elapsed: tuple[float, float]) -> dict:
    """Claude Code's working line with its timer running over real elapsed seconds."""
    return {
        "kind": "spinner",
        "word": "Thinking…",
        "at": at,
        "until": until,
        "elapsed": [round(elapsed[0], 2), round(elapsed[1], 2)],
    }


def clip(take: Take, start: float, frames: int) -> tuple[list[list[float]], list[float], float]:
    """Poses and joint speeds for every frame of a 1x clip from a take time."""
    times = [start + i / FPS for i in range(frames)]
    return [take.pose(t) for t in times], [round(take.speed(t), 2) for t in times], start


def frame_in(start: float, t: float) -> int:
    """The clip frame that shows take time t."""
    return round((t - start) * FPS)


def motion_start(take: Take, after: float, threshold: float = 2.0) -> float:
    """The first take time after a time when a joint turns faster than a threshold."""
    t = after
    while t < take.rows[-1][0]:
        if take.speed(t) > threshold:
            return t
        t += 1 / 60
    raise SystemExit(f"{take.name}: the arm never moves after {after:.2f} s")


class Script:
    """A terminal scene laid out in order, one Claude Code line after another.

    Where the edit skips a wait, Claude Code's working line stays up for a few frames and its
    timer runs over the real seconds that passed in the take.
    """

    def __init__(self, turn: float, history: list[dict] | None = None) -> None:
        """Start a scene in a turn that began at take time turn, below the lines already shown."""
        self.turn = turn
        self.last = turn
        self.frame = 0
        self.blocks: list[dict] = list(history or [])
        self.calls: list[int] = []
        self.results: list[int] = []
        self.typing: list[tuple[int, int, int]] = []

    def prompt(self, line: Line, at: int = 10, cps: int = CPS) -> None:
        """Type the prompt and submit it on the frame that stands for the moment the person sent it."""
        typed = at + round(len(line.text) / cps * FPS)
        self.blocks.append({"kind": "prompt", "text": line.text, "at": at, "submit": typed + 8, "cps": cps})
        self.typing.append((at, typed, len(line.text)))
        self.frame = typed + 8
        self.last = self.turn

    def wait(self, until: float, frames: int) -> None:
        """Hold the working line while the take runs from the last line to a later time."""
        if frames > 0:
            self.blocks.append(spinner(self.frame, self.frame + frames, (self.last - self.turn, until - self.turn)))
        self.frame += frames
        self.last = until

    def call(
        self,
        take: Take,
        line: Line,
        result: bool = True,
        gap: int = 10,
        after: int = 6,
        brand: bool = False,
        limit: int = RESULT_MAX,
    ) -> Line | None:
        """Show a tool call and, when it has arrived, its result."""
        answer = result_of(take, line) if result else None
        self.blocks.append(tool_block(line, self.frame, answer, self.frame + gap if answer else None, brand, limit))
        self.calls.append(self.frame)
        self.last = line.t
        if answer:
            self.results.append(self.frame + gap)
            self.frame += gap + after
            self.last = answer.t
        else:
            self.frame += after
        return answer

    def text(self, line: Line, hold: int) -> None:
        """Show an assistant message whole."""
        self.blocks.append(text_block(line, self.frame))
        self.frame += hold
        self.last = line.t

    def scene(self, scene_id: str, tail: int = 0) -> dict:
        """The finished scene."""
        return {"id": scene_id, "kind": "terminal", "frames": self.frame + tail, "blocks": self.blocks}


def history(take: Take, before: float) -> list[dict]:
    """Everything Claude Code already shows above a take time, complete from a scene's first frame, without OMIT."""
    out: list[dict] = []
    for line in take.lines:
        if line.t >= before:
            break
        if line.kind == "text" and any(line.text.startswith(start) for start in OMIT):
            continue
        if line.kind == "prompt":
            out.append({"kind": "prompt", "text": line.text, "at": -100, "submit": -1})
        elif line.kind == "text" and line.text.strip():
            out.append({"kind": "text", "text": line.text, "at": -100})
        elif line.kind == "tool":
            answer = next(
                (r for r in take.lines if r.kind == "result" and r.tool_id == line.tool_id and r.t < before), None
            )
            out.append(tool_block(line, -100, answer, -90 if answer else None))
    return out
