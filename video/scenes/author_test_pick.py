"""Write shots/test_pick.json, the hand-keyed pick used to compare the render stacks.

This motion is placed by inverse kinematics for the stack test only. It is not a
recording of the OpenHAL hub, and the film's real motion comes from one.

    python3 -I video/scenes/author_test_pick.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import so101_ik
import so101_urdf as urdf
from shot import SHOTS, min_jerk

CUBE_SIZE = 0.03
CUBE = (0.215, -0.07, CUBE_SIZE / 2)
GRIP_OPEN = 32.0
GRIP_HELD = 11.0
GRIP_REST = 4.0


def _deg(values: dict[str, float], gripper: float) -> dict[str, float]:
    out = {name: round(math.degrees(v), 3) for name, v in values.items()}
    out["gripper"] = gripper
    return out


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n)


def _path(
    robot: urdf.Robot,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    approach_start: tuple[float, float, float],
    approach_end: tuple[float, float, float],
    jaw: tuple[float, float, float],
    seed: dict[str, float],
    frames: tuple[int, int],
    gripper: float,
    steps: int = 8,
) -> list[dict[str, object]]:
    """Keys along a straight Cartesian move with minimum-jerk timing."""
    keys: list[dict[str, object]] = []
    values = seed
    for i in range(1, steps + 1):
        s = min_jerk(i / steps)
        point = tuple(a + (b - a) * s for a, b in zip(start, end, strict=True))
        approach = _unit(tuple(a + (b - a) * s for a, b in zip(approach_start, approach_end, strict=True)))
        values, err = so101_ik.solve(robot, point, approach=approach, jaw=jaw, seed=values)
        if err > 0.002:
            print(f"path step {i} error {err * 1000:.2f} mm")
        frame = round(frames[0] + (frames[1] - frames[0]) * i / steps)
        keys.append({"frame": frame, "joints": _deg(values, gripper), "ease": "linear"})
    return keys


def main() -> int:
    """Solve the keys and write the shot file."""
    robot = urdf.load()
    azimuth = math.atan2(CUBE[1], CUBE[0])
    jaw = (-math.sin(azimuth), math.cos(azimuth), 0.0)
    half = CUBE_SIZE / 2
    grasp = (CUBE[0] + half * jaw[0], CUBE[1] + half * jaw[1], CUBE[2])
    above = (grasp[0], grasp[1], grasp[2] + 0.06)
    lift = (0.22, -0.06, 0.14)
    tilt = _unit((0.45, -0.14, -0.88))
    down = (0.0, 0.0, -1.0)

    ready, e0 = so101_ik.best(robot, (0.17, -0.02, 0.17), approach=_unit((0.6, 0.0, -0.8)), jaw=(0.0, 1.0, 0.0))
    at, e2 = so101_ik.best(robot, grasp, jaw=jaw, seed=ready)
    pre, e1 = so101_ik.best(robot, above, jaw=jaw, seed=at)
    up, e3 = so101_ik.best(robot, lift, approach=tilt, jaw=jaw, seed=at)
    hold, e4 = so101_ik.best(
        robot, (lift[0] - 0.006, lift[1] + 0.008, lift[2] + 0.012), approach=tilt, jaw=jaw, seed=up
    )
    for label, err in (("ready", e0), ("pre", e1), ("grasp", e2), ("lift", e3), ("hold", e4)):
        print(f"{label} error {err * 1000:.2f} mm")

    shot = {
        "name": "test_pick",
        "note": "Hand-keyed test motion placed by inverse kinematics for the render stack test. Not hub data.",
        "fps": 30,
        "frames": 150,
        "resolution": [3840, 2160],
        "arm": {
            "base": [0.0, 0.0, 0.0],
            "yaw_deg": 0.0,
            "keys": [
                {"frame": 1, "joints": _deg(ready, GRIP_REST)},
                {"frame": 14, "joints": _deg(ready, GRIP_REST)},
                {"frame": 56, "joints": _deg(pre, GRIP_OPEN)},
                *_path(robot, above, grasp, down, down, jaw, pre, (56, 80), GRIP_OPEN),
                {"frame": 94, "joints": _deg(at, GRIP_HELD)},
                *_path(robot, grasp, lift, down, tilt, jaw, at, (94, 128), GRIP_HELD),
                {"frame": 150, "joints": _deg(hold, GRIP_HELD)},
            ],
        },
        "cube": {
            "size": CUBE_SIZE,
            "position": list(CUBE),
            "yaw_deg": round(math.degrees(azimuth), 3),
            "attach": 94,
            "release": None,
        },
        "camera": {
            "sensor_mm": 36.0,
            "keys": [
                {
                    "frame": 1,
                    "position": [0.86, -0.8, 0.36],
                    "target": [0.12, -0.03, 0.125],
                    "focus": [0.2, -0.06, 0.04],
                    "lens_mm": 50.0,
                    "fstop": 4.0,
                },
                {
                    "frame": 150,
                    "position": [0.72, -0.9, 0.33],
                    "target": [0.13, -0.035, 0.13],
                    "focus": [0.18, -0.04, 0.1],
                    "lens_mm": 50.0,
                    "fstop": 4.0,
                },
            ],
        },
    }
    path = SHOTS / "test_pick.json"
    path.write_text(json.dumps(shot, indent=2) + "\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
