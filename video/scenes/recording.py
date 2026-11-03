"""Read the hub recording in video/data/ and sample it at any time on the recording clock.

Pure Python, so the converter, the Blender scenes and the sound script share one reader.
Joint angles are degrees, as recorded. The gripper comes from the recorded percent,
mapped onto the gripper joint's range with 0 percent at the closed end, the same map
the device file uses. Between two 120 Hz rows every value is interpolated linearly,
so a sample never invents motion the rows don't hold.

MuJoCo fills body poses before it integrates a step, so the recorded cube and gripper
poses trail the joint angles by one physics step. pose_lag_s is that step, and
cube_at() reads the cube that much later to line it up with the joints.
"""

from __future__ import annotations

import bisect
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"
ARM = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
GRIPPER_RANGE_RAD = (-0.174533, 1.74533)


def gripper_deg(percent: float, low: float = GRIPPER_RANGE_RAD[0], high: float = GRIPPER_RANGE_RAD[1]) -> float:
    """Gripper joint angle in degrees for a percent open, 0 at the closed end."""
    return math.degrees(low + (high - low) * percent / 100.0)


def _nlerp(a: list[float], b: list[float], s: float) -> list[float]:
    if sum(x * y for x, y in zip(a, b, strict=True)) < 0.0:
        b = [-x for x in b]
    q = [x + (y - x) * s for x, y in zip(a, b, strict=True)]
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return [x / n for x in q]


@dataclass
class Beat:
    """One recorded beat: its rows at 120 Hz, its messages and its marks."""

    name: str
    file: str
    t_start: float
    t_end: float
    columns: list[str]
    rows: list[list[float]]
    messages: list[dict[str, Any]]
    marks: list[dict[str, Any]]
    pose_lag_s: float
    times: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.times = [row[0] for row in self.rows]
        self._index = {name: i for i, name in enumerate(self.columns)}

    def _bracket(self, t: float) -> tuple[list[float], list[float], float]:
        if t <= self.times[0]:
            return self.rows[0], self.rows[0], 0.0
        if t >= self.times[-1]:
            return self.rows[-1], self.rows[-1], 0.0
        k = bisect.bisect_right(self.times, t)
        a, b = self.rows[k - 1], self.rows[k]
        return a, b, (t - a[0]) / (b[0] - a[0])

    def value(self, column: str, t: float) -> float:
        """One column at time t, interpolated linearly."""
        a, b, s = self._bracket(t)
        i = self._index[column]
        return a[i] + (b[i] - a[i]) * s

    def joints_at(self, t: float) -> dict[str, float]:
        """The arm's joints in degrees at time t, with the gripper mapped from its percent."""
        out = {name: self.value(name, t) for name in ARM}
        out["gripper"] = gripper_deg(self.value("gripper", t))
        return out

    def cube_at(self, t: float) -> tuple[list[float], list[float]]:
        """The cube's world position in meters and its quaternion w, x, y, z at time t."""
        a, b, s = self._bracket(t + self.pose_lag_s)
        pi = [self._index[f"cube_{k}"] for k in "xyz"]
        qi = [self._index[f"cube_q{k}"] for k in "wxyz"]
        position = [a[i] + (b[i] - a[i]) * s for i in pi]
        return position, _nlerp([a[i] for i in qi], [b[i] for i in qi], s)

    def contains(self, t: float) -> bool:
        """Whether t falls inside the recorded rows."""
        return self.times[0] <= t <= self.times[-1]


@dataclass
class Recording:
    """Every beat on the one recording clock."""

    session: dict[str, Any]
    beats: list[Beat]

    def beat(self, name: str) -> Beat:
        """A beat by its name, such as pick-and-place."""
        for beat in self.beats:
            if beat.name == name:
                return beat
        raise KeyError(name)

    def at(self, t: float) -> Beat:
        """The beat whose rows hold time t."""
        for beat in self.beats:
            if beat.contains(t):
                return beat
        for before, after in zip(self.beats, self.beats[1:], strict=False):
            if before.times[-1] < t < after.times[0]:
                return before if t - before.times[-1] < after.times[0] - t else after
        raise ValueError(f"no recorded frame near {t} s")

    def joints_at(self, t: float) -> dict[str, float]:
        """Joints at any time on the clock, across beat boundaries."""
        return self.at(t).joints_at(t)

    def cube_at(self, t: float) -> tuple[list[float], list[float]]:
        """Cube pose at any time on the clock, across beat boundaries."""
        return self.at(t).cube_at(t)

    def messages(self, t0: float, t1: float) -> list[dict[str, Any]]:
        """Every message from t0 to t1, in order of arrival."""
        out = [m for beat in self.beats for m in beat.messages if t0 <= m["t"] <= t1]
        return sorted(out, key=lambda m: m["t"])


def load(directory: Path | str = DATA) -> Recording:
    """Read session.json and every beat file it lists."""
    directory = Path(directory)
    session = json.loads((directory / "session.json").read_text())
    lag = float(session["frames"]["timestep_s"])
    beats = []
    for entry in session["beats"]:
        raw = json.loads((directory / entry["file"]).read_text())
        beats.append(
            Beat(
                name=raw["name"],
                file=entry["file"],
                t_start=raw["t_start"],
                t_end=raw["t_end"],
                columns=raw["frames"]["columns"],
                rows=raw["frames"]["rows"],
                messages=raw["messages"],
                marks=raw.get("marks", []),
                pose_lag_s=lag,
            )
        )
    return Recording(session=session, beats=beats)
