"""Read the SO-101 URDF and compute where every link sits for a set of joint angles.

Pure Python, so the same code runs inside Blender, in a plain Python shell and in
tests. Matrices are 4 by 4 row-major nested lists. Angles are radians, as in the URDF.

The joint names are the real arm's: shoulder_pan, shoulder_lift, elbow_flex,
wrist_flex, wrist_roll and gripper. Joint zero follows the URDF's "new calibration",
where each joint's zero sits in the middle of its range.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
TOOL_LINK = "gripper_frame_link"
URDF_NAME = "so101_new_calib.urdf"
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "assets" / "so101"

Mat4 = list[list[float]]


def identity() -> Mat4:
    """Return the 4 by 4 identity."""
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def matmul(a: Mat4, b: Mat4) -> Mat4:
    """Multiply two 4 by 4 matrices."""
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def from_xyz_rpy(xyz: tuple[float, float, float], rpy: tuple[float, float, float]) -> Mat4:
    """Build a transform from a URDF origin, rotation Rz(yaw) Ry(pitch) Rx(roll)."""
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, xyz[0]],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, xyz[1]],
        [-sp, cp * sr, cp * cr, xyz[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def axis_angle(axis: tuple[float, float, float], angle: float) -> Mat4:
    """Rotation about a unit axis through the origin."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1.0 - c
    return [
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0.0],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0.0],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


@dataclass(frozen=True)
class Visual:
    """One mesh of a link, placed by its origin in the link frame."""

    mesh: str
    origin: Mat4
    material: str

    @property
    def part(self) -> str:
        """The part name, which is the mesh file name without its extension."""
        return Path(self.mesh).stem


@dataclass(frozen=True)
class Joint:
    """A joint between two links."""

    name: str
    kind: str
    parent: str
    child: str
    origin: Mat4
    axis: tuple[float, float, float]
    lower: float
    upper: float

    def clamp(self, value: float) -> float:
        """Keep a joint value inside the URDF limits."""
        if self.kind == "fixed":
            return 0.0
        return min(max(value, self.lower), self.upper)


@dataclass
class Robot:
    """The parsed URDF, with joints ordered from the base outward."""

    directory: Path
    root: str
    visuals: dict[str, list[Visual]] = field(default_factory=dict)
    joints: list[Joint] = field(default_factory=list)
    colors: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)

    def joint(self, name: str) -> Joint:
        """Look up a joint by name."""
        for joint in self.joints:
            if joint.name == name:
                return joint
        raise KeyError(name)

    def mesh_path(self, visual: Visual) -> Path:
        """Absolute path of a visual's mesh file."""
        return self.directory / visual.mesh


def _floats(text: str | None, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if not text:
        return default
    a, b, c = (float(v) for v in text.split())
    return (a, b, c)


def _origin(element: ET.Element | None) -> Mat4:
    if element is None:
        return identity()
    return from_xyz_rpy(_floats(element.get("xyz"), (0, 0, 0)), _floats(element.get("rpy"), (0, 0, 0)))


def load(directory: Path | str = DEFAULT_DIR, name: str = URDF_NAME) -> Robot:
    """Parse the URDF in directory."""
    directory = Path(directory)
    tree = ET.parse(directory / name)  # noqa: S314
    root_el = tree.getroot()
    robot = Robot(directory=directory, root="")
    for material in root_el.findall("material"):
        color = material.find("color")
        if color is not None:
            r, g, b, a = (float(v) for v in color.get("rgba", "1 1 1 1").split())
            robot.colors[material.get("name", "")] = (r, g, b, a)
    for link in root_el.findall("link"):
        visuals = []
        for visual in link.findall("visual"):
            mesh = visual.find("geometry/mesh")
            if mesh is None:
                continue
            material = visual.find("material")
            visuals.append(
                Visual(
                    mesh=mesh.get("filename", ""),
                    origin=_origin(visual.find("origin")),
                    material=material.get("name", "") if material is not None else "",
                )
            )
        robot.visuals[link.get("name", "")] = visuals
    joints = []
    for joint in root_el.findall("joint"):
        limit = joint.find("limit")
        joints.append(
            Joint(
                name=joint.get("name", ""),
                kind=joint.get("type", "fixed"),
                parent=joint.find("parent").get("link", ""),  # type: ignore[union-attr]
                child=joint.find("child").get("link", ""),  # type: ignore[union-attr]
                origin=_origin(joint.find("origin")),
                axis=_floats(joint.find("axis").get("xyz") if joint.find("axis") is not None else None, (1, 0, 0)),  # type: ignore[union-attr]
                lower=float(limit.get("lower", "0")) if limit is not None else 0.0,
                upper=float(limit.get("upper", "0")) if limit is not None else 0.0,
            )
        )
    children = {j.child for j in joints}
    roots = [name for name in robot.visuals if name not in children]
    robot.root = roots[0]
    ordered: list[Joint] = []
    frontier = [robot.root]
    while frontier:
        parent = frontier.pop(0)
        for joint in joints:
            if joint.parent == parent:
                ordered.append(joint)
                frontier.append(joint.child)
    robot.joints = ordered
    return robot


def joint_transform(joint: Joint, value: float) -> Mat4:
    """Transform from the parent link frame to the child link frame."""
    if joint.kind in ("revolute", "continuous"):
        return matmul(joint.origin, axis_angle(joint.axis, joint.clamp(value)))
    return joint.origin


def link_poses(robot: Robot, values: dict[str, float], base: Mat4 | None = None) -> dict[str, Mat4]:
    """World transform of every link for the given joint values."""
    poses = {robot.root: base or identity()}
    for joint in robot.joints:
        poses[joint.child] = matmul(poses[joint.parent], joint_transform(joint, values.get(joint.name, 0.0)))
    return poses
