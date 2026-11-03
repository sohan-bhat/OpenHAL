"""Evaluate a shot file (video/scenes/shots/*.json) frame by frame.

A shot file holds joint keys in degrees, camera keys and the props, and both the
Blender scenes and the Remotion project read the same file, so the two stacks
render the same motion. video/remotion/src/shot.ts mirrors this module.

Between two keys every value follows a minimum-jerk curve, which starts and ends
at rest the way a servo move does. A key with "ease": "linear" ends a straight
segment instead, for paths sampled densely along their own easing. Frames count
from 1.

A shot converted from the hub recording carries the cube's recorded poses as
cube.keys, one per frame, in place of the attach and release rule of a hand-keyed shot.
"""

from __future__ import annotations

import bisect
import itertools
import json
import math
from pathlib import Path
from typing import Any

import so101_urdf as urdf

SHOTS = Path(__file__).resolve().parent / "shots"


def load(name_or_path: str | Path) -> dict[str, Any]:
    """Read a shot by name (test_pick) or by path."""
    path = Path(name_or_path)
    if not path.suffix:
        path = SHOTS / f"{name_or_path}.json"
    return json.loads(path.read_text())


def min_jerk(t: float) -> float:
    """Minimum-jerk easing from 0 to 1."""
    t = min(max(t, 0.0), 1.0)
    return t * t * t * (10.0 + t * (-15.0 + 6.0 * t))


def _segment(keys: list[dict[str, Any]], frame: float) -> tuple[dict[str, Any], dict[str, Any], float]:
    if frame <= keys[0]["frame"]:
        return keys[0], keys[0], 0.0
    for a, b in itertools.pairwise(keys):
        if a["frame"] <= frame <= b["frame"]:
            span = b["frame"] - a["frame"]
            t = (frame - a["frame"]) / span if span else 1.0
            return a, b, t if b.get("ease") == "linear" else min_jerk(t)
    return keys[-1], keys[-1], 0.0


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def joints_at(shot: dict[str, Any], frame: float) -> dict[str, float]:
    """Joint values in radians at a frame, which may be fractional for motion blur."""
    a, b, t = _segment(shot["arm"]["keys"], frame)
    return {name: math.radians(_mix(a["joints"][name], b["joints"][name], t)) for name in a["joints"]}


def camera_at(shot: dict[str, Any], frame: float) -> dict[str, Any]:
    """Camera position, target, lens in millimeters, f-stop and focus point at a frame."""
    a, b, t = _segment(shot["camera"]["keys"], frame)
    out: dict[str, Any] = {}
    for field in ("position", "target", "focus"):
        out[field] = [_mix(x, y, t) for x, y in zip(a[field], b[field], strict=True)]
    for field in ("lens_mm", "fstop"):
        out[field] = _mix(a[field], b[field], t)
    out["sensor_mm"] = shot["camera"].get("sensor_mm", 36.0)
    return out


def _translate(x: float, y: float, z: float) -> urdf.Mat4:
    m = urdf.identity()
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def _inverse_rigid(m: urdf.Mat4) -> urdf.Mat4:
    r = [[m[c][r] for c in range(3)] for r in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [[*r[0], t[0]], [*r[1], t[1]], [*r[2], t[2]], [0.0, 0.0, 0.0, 1.0]]


def base_matrix(shot: dict[str, Any]) -> urdf.Mat4:
    """World transform of the arm's base link."""
    x, y, z = shot["arm"].get("base", [0.0, 0.0, 0.0])
    yaw = math.radians(shot["arm"].get("yaw_deg", 0.0))
    return urdf.matmul(_translate(x, y, z), urdf.axis_angle((0.0, 0.0, 1.0), yaw))


def tool_at(shot: dict[str, Any], robot: urdf.Robot, frame: float) -> urdf.Mat4:
    """World transform of the gripper frame at a frame."""
    return urdf.link_poses(robot, joints_at(shot, frame), base_matrix(shot))[urdf.TOOL_LINK]


def quaternion_matrix(position: list[float], q: list[float]) -> urdf.Mat4:
    """A rigid transform from a position and a unit quaternion w, x, y, z."""
    w, x, y, z = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y), position[0]],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x), position[1]],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y), position[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _recorded_cube(keys: list[dict[str, Any]], frame: float) -> urdf.Mat4:
    frames = [key["frame"] for key in keys]
    k = min(max(bisect.bisect_right(frames, frame), 1), len(keys) - 1)
    a, b = keys[k - 1], keys[k]
    t = min(max((frame - a["frame"]) / ((b["frame"] - a["frame"]) or 1), 0.0), 1.0)
    qa, qb = a["quaternion"], b["quaternion"]
    if sum(x * y for x, y in zip(qa, qb, strict=True)) < 0:
        qb = [-v for v in qb]
    q = [_mix(x, y, t) for x, y in zip(qa, qb, strict=True)]
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    position = [_mix(x, y, t) for x, y in zip(a["position"], b["position"], strict=True)]
    return quaternion_matrix(position, [v / n for v in q])


def cube_at(shot: dict[str, Any], robot: urdf.Robot, frame: float) -> urdf.Mat4:
    """World transform of the cube, recorded, or riding with the gripper from attach until release."""
    cube = shot["cube"]
    if "keys" in cube:
        return _recorded_cube(cube["keys"], frame)
    start = urdf.matmul(_translate(*cube["position"]), urdf.axis_angle((0.0, 0.0, 1.0), math.radians(cube["yaw_deg"])))
    attach = cube.get("attach")
    release = cube.get("release")
    if attach is None or frame < attach:
        return start
    held_until = min(frame, release) if release is not None else frame
    grip = urdf.matmul(_inverse_rigid(tool_at(shot, robot, attach)), start)
    return urdf.matmul(tool_at(shot, robot, held_until), grip)
