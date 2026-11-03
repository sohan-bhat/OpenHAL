"""Build the stack test shot (SO-101 picks up a cube) and render it headless.

    Blender -b --factory-startup -noaudio --python video/scenes/test_shot.py -- \\
        --engine cycles --width 3840 --height 2160 --samples 48 --frames 1-150 \\
        --out video/out/test/blender-cycles-4k

Every object, material, light, camera move and keyframe comes from this script,
the modules next to it, look.json and shots/test_pick.json. Frames are written as
PNG files named frame_0001.png and so on, and each frame's render time is
appended to times.csv in the output folder.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import shot as shotlib
import so101_blender
import so101_urdf as urdf
import studio_blender as studio
from mathutils import Matrix, Vector

LIGHT_WATTS = {
    "cycles": {"key": 13.0, "rim": 13.0, "fill": 1.6, "wash": 4.0},
    "eevee": {"key": 13.0, "rim": 13.0, "fill": 1.6, "wash": 4.0},
}


def parse_frames(text: str, last: int) -> list[int]:
    """Parse 1-150, 1,16,31 or 1-150:15 into frame numbers."""
    frames: list[int] = []
    for part in text.split(","):
        step = 1
        if ":" in part:
            part, step_text = part.split(":")
            step = int(step_text)
        if "-" in part:
            a, b = part.split("-")
            frames.extend(range(int(a), min(int(b), last) + 1, step))
        else:
            frames.append(int(part))
    return frames


def args() -> argparse.Namespace:
    """Arguments after the -- separator."""
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    p.add_argument("--shot", default="test_pick")
    p.add_argument("--width", type=int, default=3840)
    p.add_argument("--height", type=int, default=2160)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--frames", default="1-150")
    p.add_argument("--out", required=True)
    p.add_argument(
        "--edge-bevel", type=int, default=0, help="Cycles bevel shader samples for rounded edges, 0 for none"
    )
    p.add_argument("--save-blend", action="store_true")
    return p.parse_args(argv)


def build(shot: dict, engine: str, edge_bevel: int = 0) -> None:
    """Create the whole scene and its keyframes."""
    look = studio.load_look()
    studio.reset()
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    mats = studio.materials(look, edge_bevel)
    robot = urdf.load()
    arm = so101_blender.build(robot, mats)
    arm.root.matrix_world = Matrix(shotlib.base_matrix(shot))
    cables = so101_blender.add_cables(mats["cable"])
    first = shotlib.camera_at(shot, 1)
    studio.desk_and_backdrop(look, mats, Vector(first["position"]), Vector(first["target"]))
    studio.lights(look, LIGHT_WATTS[engine])
    studio.world(look)
    cam = studio.camera()

    size = shot["cube"]["size"]
    bpy.ops.mesh.primitive_cube_add(size=size)
    cube = bpy.context.object
    cube.name = "cube"
    bevel = cube.modifiers.new("bevel", "BEVEL")
    bevel.width = look["materials"]["cube"]["bevel"]
    bevel.segments = 4
    cube.data.shade_smooth()
    cube.data.materials.append(mats["cube"])
    cube.rotation_mode = "QUATERNION"

    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, shot["frames"]
    base = shotlib.base_matrix(shot)
    for frame in range(1, shot["frames"] + 1):
        joints = shotlib.joints_at(shot, frame)
        arm.pose(joints)
        arm.key(frame)
        poses = urdf.link_poses(robot, joints, base)
        for cable in cables:
            cable.key(poses, frame)
        m = Matrix(shotlib.cube_at(shot, robot, frame))
        cube.location = m.to_translation()
        cube.rotation_quaternion = m.to_quaternion()
        cube.keyframe_insert("location", frame=frame)
        cube.keyframe_insert("rotation_quaternion", frame=frame)
        studio.key_camera(cam, shotlib.camera_at(shot, frame), frame)


def main() -> int:
    """Build, then render the requested frames one by one with timings."""
    opts = args()
    shot = shotlib.load(opts.shot)
    build(shot, opts.engine, opts.edge_bevel)
    studio.render_settings(opts.engine, opts.width, opts.height, opts.samples, shot["fps"])
    out = Path(opts.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if opts.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
    scene = bpy.context.scene
    times = out / "times.csv"
    if not times.exists():
        times.write_text("engine,width,height,samples,frame,seconds\n")
    for frame in parse_frames(opts.frames, shot["frames"]):
        scene.frame_set(frame)
        scene.render.filepath = str(out / f"frame_{frame:04d}.png")
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        seconds = time.perf_counter() - start
        with times.open("a") as handle:
            handle.write(f"{opts.engine},{opts.width},{opts.height},{opts.samples},{frame},{seconds:.2f}\n")
        print(f"frame {frame} {seconds:.2f} s", flush=True)
    return 0


if __name__ == "__main__":
    main()
