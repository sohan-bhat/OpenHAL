"""Check that the render model and the recorded model put every SO-101 part in the same place.

The film draws the arm from The Robot Studio's URDF (so101_urdf.py), while the hub recording
ran MuJoCo Menagerie's robotstudio_so101. This script loads both and compares them.

1. Body poses. Every recorded frame's joint angles go through MuJoCo's forward kinematics
   and through so101_urdf.link_poses(), and every body's position and rotation are compared.
2. Mesh placement. At several recorded poses every visual mesh is placed by each model, and the
   bounds and centroid of its world vertices are compared. MuJoCo recenters each mesh on its
   inertial frame, so geom frames differ from STL origins, while the vertices must agree.
3. The recording itself. The recorded gripper body pose is compared with the URDF pose for the
   recorded joint angles, read one physics step earlier, which is when MuJoCo filled it.

    uv run --extra mujoco python video/scenes/check_model.py --cache video/assets/menagerie
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hub"))

import menagerie
import recording
import so101_urdf as urdf

POSITION_MM = 0.01
"""Largest allowed difference in any body or mesh position, in millimeters."""
ROTATION_DEG = 0.01
"""Largest allowed difference in any body rotation, in degrees."""
RECORDED_MM = 0.2
"""Largest allowed difference from the recorded gripper pose. The pose is rounded to 0.01 mm, and the
joints one step earlier come from halfway between two 120 Hz rows, which drifts a little where a joint
changes speed fast."""
BODIES = {
    "base": "base_link",
    "shoulder": "shoulder_link",
    "upper_arm": "upper_arm_link",
    "lower_arm": "lower_arm_link",
    "wrist": "wrist_link",
    "gripper": "gripper_link",
    "moving_jaw_so101_v1": "moving_jaw_so101_v1_link",
}
JOINTS = (*recording.ARM, "gripper")


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    c = (np.trace(a.T @ b) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _stl_vertices(path: Path) -> np.ndarray:
    data = path.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    facets = np.frombuffer(data[84 : 84 + count * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return np.unique(facets["v"].reshape(-1, 3).astype(np.float64), axis=0)


def _radians(row: list[float], columns: list[str]) -> list[float]:
    return [math.radians(row[columns.index(name if name != "gripper" else "gripper_jaw")]) for name in JOINTS]


def check_bodies(model: mujoco.MjModel, data: mujoco.MjData, robot: urdf.Robot, rec: recording.Recording) -> str:
    worst_mm = worst_deg = 0.0
    frames = 0
    for beat in rec.beats:
        for row in beat.rows:
            q = _radians(row, beat.columns)
            data.qpos[:] = q
            mujoco.mj_kinematics(model, data)
            poses = urdf.link_poses(robot, dict(zip(JOINTS, q, strict=True)))
            for body, link in BODIES.items():
                i = model.body(body).id
                pose = np.array(poses[link])
                worst_mm = max(worst_mm, float(np.linalg.norm(pose[:3, 3] - data.xpos[i])) * 1000.0)
                worst_deg = max(worst_deg, _angle_deg(pose[:3, :3], data.xmat[i].reshape(3, 3)))
            frames += 1
    assert worst_mm <= POSITION_MM, f"a body is {worst_mm:.4f} mm apart"
    assert worst_deg <= ROTATION_DEG, f"a body is turned {worst_deg:.4f} deg apart"
    return f"{len(BODIES)} bodies in {frames} recorded frames, at most {worst_mm:.4f} mm and {worst_deg:.4f} deg apart"


def check_meshes(model: mujoco.MjModel, data: mujoco.MjData, robot: urdf.Robot, rec: recording.Recording) -> str:
    rows = [beat.rows[len(beat.rows) // 2] for beat in rec.beats] + [rec.beats[0].rows[0]]
    columns = rec.beats[0].columns
    cache: dict[str, np.ndarray] = {}
    worst = 0.0
    compared = 0
    skipped = set()
    for row in rows:
        q = _radians(row, columns)
        data.qpos[:] = q
        mujoco.mj_kinematics(model, data)
        poses = urdf.link_poses(robot, dict(zip(JOINTS, q, strict=True)))
        for g in range(model.ngeom):
            if model.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or model.geom_group[g] != 2:
                continue
            body = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, model.geom_bodyid[g])
            mesh_id = model.geom_dataid[g]
            mesh = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, mesh_id)
            link = BODIES.get(body)
            if link is None:
                skipped.add(f"{body} ({mesh})")
                continue
            start, count = model.mesh_vertadr[mesh_id], model.mesh_vertnum[mesh_id]
            world = (
                data.geom_xpos[g]
                + model.mesh_vert[start : start + count].astype(np.float64) @ data.geom_xmat[g].reshape(3, 3).T
            )
            best = math.inf
            for visual in robot.visuals[link]:
                if visual.part != mesh:
                    continue
                if mesh not in cache:
                    cache[mesh] = _stl_vertices(robot.mesh_path(visual))
                place = np.array(urdf.matmul(poses[link], visual.origin))
                ours = cache[mesh] @ place[:3, :3].T + place[:3, 3]
                gap = max(
                    np.abs(ours.min(0) - world.min(0)).max(),
                    np.abs(ours.max(0) - world.max(0)).max(),
                    np.abs(ours.mean(0) - world.mean(0)).max(),
                )
                best = min(best, float(gap) * 1000.0)
            assert best <= POSITION_MM, f"{mesh} on {body} is {best:.4f} mm apart"
            worst = max(worst, best)
            compared += 1
    note = f", Menagerie only: {', '.join(sorted(skipped))}" if skipped else ""
    return f"{compared} mesh placements at {len(rows)} poses, bounds and centroids at most {worst:.4f} mm apart{note}"


def check_recorded(robot: urdf.Robot, rec: recording.Recording) -> str:
    worst = 0.0
    for beat in rec.beats:
        cols = beat.columns
        for before, after in zip(beat.rows, beat.rows[1:], strict=False):
            q = {}
            for name in recording.ARM:
                i = cols.index(name)
                q[name] = math.radians(after[i] - (after[i] - before[i]) * 0.5)
            pose = urdf.link_poses(robot, q)["gripper_link"]
            recorded = [after[cols.index(f"gripper_{k}")] for k in "xyz"]
            worst = max(worst, math.dist([pose[i][3] for i in range(3)], recorded) * 1000.0)
    assert worst <= RECORDED_MM, f"the recorded gripper is {worst:.4f} mm from the URDF pose"
    return f"recorded gripper body within {worst:.4f} mm of the URDF pose one physics step earlier"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True, help="folder for the pinned Menagerie files")
    opts = parser.parse_args()
    folder = menagerie.fetch(Path(opts.cache))
    model = mujoco.MjModel.from_xml_path(str(folder / "so101.xml"))
    data = mujoco.MjData(model)
    robot = urdf.load()
    rec = recording.load()
    failed = 0
    for name, check in (
        ("bodies", lambda: check_bodies(model, data, robot, rec)),
        ("meshes", lambda: check_meshes(model, data, robot, rec)),
        ("recording", lambda: check_recorded(robot, rec)),
    ):
        try:
            print(f"ok    {name}: {check()}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
