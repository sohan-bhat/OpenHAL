"""Servo cables for the SO-101: where each cable leaves one servo and enters the next.

Each end is a point on a servo housing in that servo's own mesh frame, plus a
tangent that says which way the cable leaves the connector. anchors() turns them
into link-frame points, and points() samples the cubic Bezier between the two ends
for any pose, so the cable follows both links as the joints turn. The Remotion
project reads the same link-frame anchors from cables.json.

    python3 -I video/scenes/so101_cables.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import so101_urdf as urdf

OUT = Path(__file__).resolve().parent / "cables.json"
RADIUS = 0.0016

SPEC: list[dict[str, Any]] = [
    {
        "name": "pan_to_lift",
        "from": {"link": "base_link", "servo": 0, "point": [-0.021, 0.0, -0.012], "tangent": [-0.03, 0.0, 0.0]},
        "to": {"link": "shoulder_link", "servo": 0, "point": [-0.021, 0.0, -0.012], "tangent": [-0.035, 0.0, 0.0]},
    },
    {
        "name": "lift_to_elbow",
        "from": {"link": "shoulder_link", "servo": 0, "point": [-0.021, 0.008, -0.012], "tangent": [-0.03, 0.0, -0.01]},
        "to": {"link": "upper_arm_link", "servo": 0, "point": [-0.021, 0.0, -0.012], "tangent": [-0.04, 0.0, 0.0]},
    },
    {
        "name": "elbow_to_wrist",
        "from": {
            "link": "upper_arm_link",
            "servo": 0,
            "point": [-0.021, 0.008, -0.012],
            "tangent": [-0.03, 0.0, -0.01],
        },
        "to": {"link": "lower_arm_link", "servo": 0, "point": [-0.021, 0.0, -0.012], "tangent": [-0.04, 0.0, 0.0]},
    },
    {
        "name": "wrist_to_roll",
        "from": {
            "link": "lower_arm_link",
            "servo": 0,
            "point": [-0.021, 0.008, -0.012],
            "tangent": [-0.025, 0.0, -0.01],
        },
        "to": {"link": "wrist_link", "servo": 0, "point": [-0.021, 0.0, -0.012], "tangent": [-0.03, 0.0, 0.0]},
    },
]


def _servos(robot: urdf.Robot, link: str) -> list[urdf.Visual]:
    return [v for v in robot.visuals[link] if v.material == "sts3215"]


def _apply(m: urdf.Mat4, p: list[float], w: float) -> list[float]:
    return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] * w for i in range(3)]


def anchors(robot: urdf.Robot) -> list[dict[str, Any]]:
    """Cable ends in link frames: point and tangent, both in meters."""
    out = []
    for cable in SPEC:
        entry: dict[str, Any] = {"name": cable["name"], "radius": RADIUS}
        for end in ("from", "to"):
            spec = cable[end]
            origin = _servos(robot, spec["link"])[spec["servo"]].origin
            entry[end] = {
                "link": spec["link"],
                "point": [round(v, 6) for v in _apply(origin, spec["point"], 1.0)],
                "tangent": [round(v, 6) for v in _apply(origin, spec["tangent"], 0.0)],
            }
        out.append(entry)
    return out


def load() -> list[dict[str, Any]]:
    """Read cables.json."""
    return json.loads(OUT.read_text())["cables"]


def points(
    cable: dict[str, Any], poses: dict[str, urdf.Mat4]
) -> tuple[list[float], list[float], list[float], list[float]]:
    """World Bezier control points P0, P1, P2, P3 of one cable for the given link poses."""
    a, b = cable["from"], cable["to"]
    ma, mb = poses[a["link"]], poses[b["link"]]
    p0 = _apply(ma, a["point"], 1.0)
    p3 = _apply(mb, b["point"], 1.0)
    ta = _apply(ma, a["tangent"], 0.0)
    tb = _apply(mb, b["tangent"], 0.0)
    p1 = [p0[i] + ta[i] for i in range(3)]
    p2 = [p3[i] + tb[i] for i in range(3)]
    return p0, p1, p2, p3


def main() -> int:
    """Write cables.json from SPEC and the URDF."""
    robot = urdf.load()
    OUT.write_text(json.dumps({"cables": anchors(robot)}, indent=2) + "\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
