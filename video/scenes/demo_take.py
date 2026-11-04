"""Read one recorded take of the demo session from video/data/<take>/.

A take holds the Claude Code stream, its arrival times, the hub's messages, the arm's joint frames
and the Inspector clicks, all on one clock in seconds since the take began. This module loads them
and turns the stream into the lines Claude Code shows, so the demo's edit can quote them exactly.

    python3 -I video/scenes/demo_take.py take-3

prints the transcript with the time of every line.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path

VIDEO = Path(__file__).resolve().parent.parent
DATA = VIDEO / "data"
POSE = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper_jaw"]
CUBE = ["cube_x", "cube_y", "cube_z", "cube_qw", "cube_qx", "cube_qy", "cube_qz"]
SPEED = ["shoulder_pan", "shoulder_lift", "elbow_flex"]
PHYSICS_STEP = 1 / 240


def jsonl(path: Path) -> list[dict]:
    """Every JSON object in a JSON lines file."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class Line:
    """One thing Claude Code shows, at the take time it arrived."""

    t: float
    kind: str
    text: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    result: str = ""
    error: bool = False
    tool_id: str = ""


@dataclass
class Take:
    """A loaded take."""

    name: str
    folder: Path
    session: dict
    columns: list[str]
    rows: list[list[float]]
    lines: list[Line]
    live: list[dict]
    audit: list[dict]
    marks: list[dict]
    inspector: list[dict]

    def column(self, name: str) -> int:
        """Index of a frame column."""
        return self.columns.index(name)

    def value(self, name: str, t: float) -> float:
        """A frame column at clock time t, linearly interpolated between the two nearest rows.

        A row's own t is simulated time. The row happened on the clock at t plus its lag_ms, so
        the arm lines up with the clicks, the hub's messages and Claude Code's lines.
        """
        i = self.column(name)
        times = self._times
        k = bisect_right(times, t)
        if k <= 0:
            return self.rows[0][i]
        if k >= len(times):
            return self.rows[-1][i]
        a, b = self.rows[k - 1], self.rows[k]
        span = times[k] - times[k - 1]
        f = (t - times[k - 1]) / span if span > 0 else 0.0
        return a[i] + (b[i] - a[i]) * f

    @property
    def _times(self) -> list[float]:
        cached = getattr(self, "_cache", None)
        if cached is None:
            lag = self.column("lag_ms")
            cached = []
            for row in self.rows:
                clock = row[0] + row[lag] / 1000
                cached.append(max(clock, cached[-1] + 1e-6) if cached else clock)
            object.__setattr__(self, "_cache", cached)
        return cached

    def pose(self, t: float) -> list[float]:
        """Joint angles and gripper jaw in degrees, then the cube's position and quaternion, at take time t."""
        joints = [round(self.value(name, t), 4) for name in POSE]
        cube = [self.value(name, t + PHYSICS_STEP) for name in CUBE]
        norm = sum(q * q for q in cube[3:]) ** 0.5 or 1.0
        cube = [round(v, 5) for v in cube[:3]] + [round(q / norm, 5) for q in cube[3:]]
        return joints + cube

    def sim_time(self, t: float) -> float:
        """The simulated time of the frame the clock shows at clock time t."""
        return self.value("t", t)

    def sim_value(self, name: str, s: float) -> float:
        """A frame column at simulated time s."""
        i = self.column(name)
        k = bisect_right(self._sim, s)
        if k <= 0:
            return self.rows[0][i]
        if k >= len(self._sim):
            return self.rows[-1][i]
        a, b = self.rows[k - 1], self.rows[k]
        span = b[0] - a[0]
        f = (s - a[0]) / span if span > 0 else 0.0
        return a[i] + (b[i] - a[i]) * f

    @property
    def _sim(self) -> list[float]:
        cached = getattr(self, "_sim_cache", None)
        if cached is None:
            cached = [row[0] for row in self.rows]
            object.__setattr__(self, "_sim_cache", cached)
        return cached

    def speed(self, t: float, window: float = 2 / 60) -> float:
        """The fastest of the pan, lift and elbow joints at clock time t, in deg/s of simulated time."""
        s = self.sim_time(t)
        return max(abs(self.sim_value(n, s + window) - self.sim_value(n, s - window)) / (2 * window) for n in SPEED)

    def mark(self, text: str, nth: int = 0) -> dict:
        """The nth mark whose text starts with text."""
        found = [m for m in self.marks if m.get("text", "").startswith(text)]
        if len(found) <= nth:
            raise SystemExit(f"{self.name} has no mark {text!r} number {nth + 1}")
        return found[nth]


def tool_text(content: object) -> str:
    """The text of a tool result block."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def transcript(stream: list[dict], times: dict[int, float]) -> list[Line]:
    """The lines Claude Code shows for a stream-json session, in order."""
    out: list[Line] = []
    for number, event in enumerate(stream, 1):
        t = times.get(number)
        kind = event.get("type")
        if t is None:
            continue
        if kind == "user":
            content = event["message"]["content"]
            if isinstance(content, str):
                out.append(Line(t, "prompt", text=content))
                continue
            for block in content:
                if block.get("type") == "text":
                    out.append(Line(t, "prompt", text=block["text"]))
                elif block.get("type") == "tool_result":
                    out.append(
                        Line(
                            t,
                            "result",
                            result=tool_text(block.get("content")),
                            error=bool(block.get("is_error")),
                            tool_id=block.get("tool_use_id", ""),
                        )
                    )
        elif kind == "assistant":
            for block in event["message"]["content"]:
                if block.get("type") == "text":
                    out.append(Line(t, "text", text=block["text"]))
                elif block.get("type") == "thinking":
                    out.append(Line(t, "thinking", text=block.get("thinking", "")))
                elif block.get("type") == "tool_use":
                    out.append(
                        Line(t, "tool", tool=block["name"], args=block.get("input", {}), tool_id=block.get("id", ""))
                    )
        elif kind == "result":
            out.append(Line(t, "end", text=str(event.get("subtype", ""))))
    return out


def load(name: str) -> Take:
    """Load video/data/<name>/."""
    folder = DATA / name
    session = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    with gzip.open(folder / "frames.csv.gz", "rt", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        columns = next(reader)
        rows = [[float(v) for v in row] for row in reader if row]
    rows.sort(key=lambda row: row[0])
    stream = jsonl(folder / "claude.stream.jsonl")
    times = {entry["line"]: entry["t"] for entry in jsonl(folder / "claude.times.jsonl")}
    return Take(
        name=name,
        folder=folder,
        session=session,
        columns=columns,
        rows=rows,
        lines=transcript(stream, times),
        live=jsonl(folder / "hub-live.jsonl"),
        audit=jsonl(folder / "hub-audit.jsonl"),
        marks=jsonl(folder / "marks.jsonl"),
        inspector=jsonl(folder / "inspector.jsonl"),
    )


def main() -> int:
    """Print a take's transcript with times."""
    take = load(sys.argv[1] if len(sys.argv) > 1 else "take-1")
    for line in take.lines:
        if line.kind == "tool":
            print(f"{line.t:8.3f} tool    {line.tool} {json.dumps(line.args)[:160]}")
        elif line.kind == "result":
            print(f"{line.t:8.3f} result  {'error ' if line.error else ''}{line.result[:160]!r}")
        else:
            print(f"{line.t:8.3f} {line.kind:7} {line.text[:160]!r}")
    print(f"{len(take.rows)} frames from {take.rows[0][0]:.3f} to {take.rows[-1][0]:.3f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
