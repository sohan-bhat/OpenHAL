"""Build one shot of the launch film in Blender from its shot file, and render it headless.

    Blender -b --factory-startup -noaudio --python video/scenes/film_shot.py -- \\
        --shot s3-pick --aspect landscape --width 960 --height 540 --samples 8 \\
        --out video/out/frames/s3-pick-landscape

The arm, the gripper and the cube follow the shot's recorded keys. Everything else on the set
follows the shot's hub events. A command leaves the agent's display as a pulse of light along
its cable at the frame the agent sent it. A command the hub passes runs on along the layer
and down the arm's cable. One the hub blocks stops at the layer, and one held for a person
stays there until the hub confirms the approval. STOP flashes the layer and runs to every
device. The phone wakes when the hub holds an action, fills when the person approves and
shows STOP when the person presses it. Each device lights when the hub's connect event comes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy
import film_props as props
import shot as shotlib
import so101_blender
import so101_urdf as urdf
import studio_blender as studio
from mathutils import Matrix, Vector

FILM = Path(__file__).resolve().parent / "shots" / "film"
LIGHT_WATTS = {"key": 13.0, "rim": 13.0, "fill": 1.6, "wash": 4.0}
COMMANDS = {"action", "write"}
QUERIES = {"read_many", "list_devices", "wait_until", "get_confirmation_status", "hub_status"}
DEVICE_PROPS = ("printer", "board", "psu")
TRAIL_M = 0.09


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
    p.add_argument("--shot", required=True)
    p.add_argument("--aspect", choices=("landscape", "vertical"), default="landscape")
    p.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--height", type=int, default=540)
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--frames", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--edge-bevel", type=int, default=0)
    p.add_argument("--save-blend", action="store_true")
    return p.parse_args(argv)


def ease(x: float) -> float:
    """Minimum-jerk easing on 0 to 1."""
    return shotlib.min_jerk(x)


def ramp(frame: float, start: float, length: float) -> float:
    """0 before start, 1 after start plus length, eased between."""
    if length <= 0:
        return 1.0 if frame >= start else 0.0
    return ease((frame - start) / length)


def decay(frame: float, at: float, frames: float = 12.0) -> float:
    """A flash at frame at that fades over about frames."""
    if frame < at:
        return 0.0
    return math.exp(-(frame - at) / (frames / 3.0))


class Track:
    """Per-frame levels for one keyed value, starting from a base level."""

    def __init__(self, frames: int, base: float) -> None:
        self.values = [base] * (frames + 2)

    def set_from(self, start: float, value: float) -> None:
        """Set the level from a frame onward."""
        for f in range(len(self.values)):
            if f >= start:
                self.values[f] = value

    def add(self, fn: Any) -> None:
        """Add fn(frame) to every frame."""
        for f in range(len(self.values)):
            self.values[f] += fn(f)

    def mul(self, fn: Any) -> None:
        """Multiply every frame by fn(frame)."""
        for f in range(len(self.values)):
            self.values[f] *= fn(f)


class Pulse:
    """One message as a bead of light: legs along paths, with holds between them."""

    def __init__(self, obj: bpy.types.Object, glow: props.Glow) -> None:
        self.obj = obj
        self.glow = glow
        self.steps: list[tuple[str, float, float, Any]] = []
        self.blocked_from: float | None = None

    def leg(self, start: float, frames: float, path: props.Path3, reverse: bool, cable: Any | None) -> float:
        """Travel a path from start for frames, return the arrival frame."""
        self.steps.append(("move", start, start + frames, (path, reverse, cable)))
        return start + frames

    def hold(self, start: float, end: float, point: Vector, breathe: bool) -> float:
        """Wait at a point until end."""
        self.steps.append(("hold", start, end, (point, breathe)))
        return end

    def state(self, frame: float) -> tuple[Vector | None, float]:
        """Where the bead is and how bright, or None when it isn't on screen."""
        for kind, a, b, data in self.steps:
            if a <= frame <= b:
                if kind == "move":
                    path, reverse, _ = data
                    s = (frame - a) / max(b - a, 1e-6)
                    return path.at(1.0 - s if reverse else s), 1.0
                point, breathe = data
                level = 0.75 + 0.25 * math.cos((frame - a) * 2 * math.pi / 36.0) if breathe else 0.8
                return point, level
        return None, 0.0


def load(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """A shot file and the edit it belongs to."""
    shot = json.loads((FILM / f"{name}.json").read_text())
    edit = json.loads((FILM / "edit.json").read_text())
    return shot, edit


def first_after(events: list[dict[str, Any]], t: float, **want: Any) -> dict[str, Any] | None:
    """The first event after time t with the given fields."""
    for e in events:
        if e["t"] > t and all(e.get(k) == v for k, v in want.items()):
            return e
    return None


def build(shot: dict[str, Any], edit: dict[str, Any], aspect: str, engine: str, edge_bevel: int = 0) -> None:
    """Create the whole set for one shot and key every frame."""
    look = studio.load_look()
    studio.reset()
    for block in list(bpy.data.objects):
        bpy.data.objects.remove(block, do_unlink=True)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    accent = look["palette"]["accent"]
    layout = edit["layout"]
    fps = shot["fps"]
    frames = shot["frames"]
    cast = set(shot["set"])
    mats = props.film_materials(look, studio.materials(look, edge_bevel))
    robot = urdf.load()
    arm = so101_blender.build(robot, mats)
    servo_cables = so101_blender.add_cables(mats["cable"])
    camera_spec = shot["camera_vertical"] if aspect == "vertical" else shot["camera"]
    cam_shot = {"camera": camera_spec}
    first = shotlib.camera_at(cam_shot, 1)
    studio.desk_and_backdrop(look, mats, Vector(first["position"]), Vector(first["target"]))
    lights = studio.lights(look, LIGHT_WATTS)
    studio.world(look)
    cam = studio.camera()

    size = layout["cube_size"]
    cube = props.box("cube", (size, size, size), (0.0, 0.0, size / 2), mats["cube"], look["materials"]["cube"]["bevel"])
    cube.rotation_mode = "QUATERNION"
    if "bin" in cast:
        props.build_bin(layout["bin"], mats["tray"])

    speed = layout["pulse_speed_m_s"]
    radius = layout["cable_radius"]
    tracks: list[tuple[Any, Track]] = []

    def track(target: Any, base: float) -> Track:
        t = Track(frames, base)
        tracks.append((target, t))
        return t

    agent = layer = phone = None
    cables: dict[str, props.Cable] = {}
    ports: dict[str, Track] = {}
    port_x: dict[str, float] = {}
    devices: dict[str, props.Device] = {}
    device_tracks: dict[str, list[Track]] = {}
    events = shot["events"]

    if "layer" in cast:
        layer = props.build_layer(layout["layer"], accent)
    if "agent" in cast:
        agent = props.build_agent(layout["agent"], mats, accent)
    if "phone" in cast:
        phone = props.build_phone(layout["phone"], mats, accent)
    if "devices" in cast:
        devices["printer"] = props.build_printer(layout["printer"], mats)
        devices["board"] = props.build_board(layout["board"], mats)
        devices["psu"] = props.build_psu(layout["psu"], mats)

    trail_glow = props.glow("trail", "#fff4fa", 9.0)
    if layer is not None:
        ends: dict[str, Vector] = {"arm": Vector((*layout["arm_port"], 0.0))}
        if agent is not None:
            ends["agent"] = agent.base_point
        for name, device in devices.items():
            ends[name] = device.cable_point
        for name, start in ends.items():
            port_x[name] = start.x
            props.add_port(layer, name, start.x, mats["port"], accent)
            port = layer.port_point(name)
            cables[name] = props.desk_cable(f"link.{name}", start, port, radius, mats["cable"], trail_glow)
            ring = layer.ports[name][1]
            ports[name] = track(ring, 0.35)

    def leg_frames(length: float) -> float:
        return max(length / speed * fps, 1.0)

    def port_point(name: str) -> Vector:
        p = layer.port_point(name)
        return Vector((p.x, p.y, radius + 0.002))

    def along(a: str, b: str) -> props.Path3:
        return props.Path3([port_point(a), port_point(b)])

    pulses: list[Pulse] = []

    def new_pulse() -> Pulse:
        g = props.glow(f"pulse.{len(pulses)}", "#fff6fb", 40.0)
        obj = props.sphere(f"pulse.{len(pulses)}", radius * 1.7, g.material)
        props.no_shadow(obj)
        p = Pulse(obj, g)
        pulses.append(p)
        return p

    def flash_port(name: str, at: float, strength: float = 3.0, frames_: float = 14.0) -> None:
        if name in ports:
            ports[name].add(lambda f: strength * decay(f, at, frames_))

    line_track = track(layer.line_glow, 1.0) if layer is not None else None
    sheet_track = track(layer.sheet_glow, 1.0) if layer is not None else None

    if layer is not None and agent is not None:
        for e in events:
            if e["source"] != "agent" or e["kind"] != "request":
                continue
            start = e["frame"]
            if e.get("tool") in COMMANDS and e.get("device") == "arm":
                answer = first_after(events, e["t"] - 1e-6, source="hub", via="mcp", kind="response", tool=e["tool"])
                status = answer["status"] if answer else "done"
                p = new_pulse()
                at_layer = p.leg(start, leg_frames(cables["agent"].path.length), cables["agent"].path, False, "agent")
                flash_port("agent", at_layer, 2.5)
                if status == "blocked":
                    p.hold(at_layer, frames + 2, port_point("agent"), breathe=False)
                    p.blocked_from = at_layer
                    flash_port("agent", at_layer, 6.0, 40.0)
                    continue
                go = at_layer
                if status == "pending":
                    confirm = first_after(events, e["t"], source="hub", via="live", audit="confirm")
                    go = confirm["frame"] if confirm else frames + 2
                    p.hold(at_layer, go, port_point("agent"), breathe=True)
                    if confirm:
                        flash_port("agent", go, 4.0)
                cross = along("agent", "arm")
                at_arm_port = p.leg(go, leg_frames(cross.length), cross, False, None)
                flash_port("arm", at_arm_port, 2.5)
                p.leg(at_arm_port, leg_frames(cables["arm"].path.length), cables["arm"].path, True, "arm")
            elif e.get("tool") in QUERIES or e.get("tool") in COMMANDS:
                p = new_pulse()
                at_layer = p.leg(start, leg_frames(cables["agent"].path.length), cables["agent"].path, False, "agent")
                flash_port("agent", at_layer, 2.5)

    if layer is not None:
        for e in events:
            if e.get("audit") == "stop":
                at = e["frame"]
                line_track.add(lambda f, at=at: 2.2 * decay(f, at, 20.0))
                sheet_track.add(lambda f, at=at: 1.6 * decay(f, at, 20.0))
                for name, cable in cables.items():
                    if name == "agent":
                        continue
                    flash_port(name, at, 4.0)
                    p = new_pulse()
                    p.leg(at, leg_frames(cable.path.length), cable.path, True, name)

    if "devices" in cast and layer is not None:
        for name in DEVICE_PROPS:
            device = devices[name]
            levels = [track(g, 0.0) for g in device.lights]
            device_tracks[name] = levels
            plugged = next(
                (
                    e
                    for e in events
                    if e["source"] == "mark"
                    and e["text"].startswith({"printer": "printer", "board": "plant-waterer", "psu": "bench-psu"}[name])
                ),
                None,
            )
            register = next((e for e in events if e.get("audit") == "register" and e.get("device") == name), None)
            connect = next((e for e in events if e.get("audit") == "connect" and e.get("device") == name), None)
            ports[name].values = [0.0] * len(ports[name].values)
            if plugged is not None:
                cables[name].obj["plug_frame"] = plugged["frame"]
            if register is not None:
                p = new_pulse()
                p.leg(register["frame"], leg_frames(cables[name].path.length), cables[name].path, True, name)
                ports[name].set_from(register["frame"], 0.12)
            if connect is not None:
                at = connect["frame"]
                for lv in levels:
                    lv.add(lambda f, at=at: ramp(f, at, 6.0))
                ports[name].set_from(at, 0.35)
                flash_port(name, at, 4.0, 18.0)
                p = new_pulse()
                p.leg(at, leg_frames(cables[name].path.length), cables[name].path, False, name)
    elif devices:
        for name in DEVICE_PROPS:
            for g in devices[name].lights:
                track(g, 1.0)

    phone_tracks = {}
    if phone is not None:
        phone_tracks = {
            "screen": track(phone.screen, 0.0),
            "ring": track(phone.ring, 0.0),
            "fill": track(phone.fill, 0.0),
            "stop": track(phone.stop, 0.0),
        }
        held = next((e for e in events if e.get("kind") == "response" and e.get("status") == "pending"), None)
        approve = next(
            (e for e in events if str(e.get("path", "")).endswith("/approve") and e["kind"] == "request"), None
        )
        stop = next((e for e in events if e.get("path") == "/v1/stop" and e["kind"] == "request"), None)
        if held is not None:
            at = held["frame"]
            phone_tracks["screen"].add(lambda f, at=at: ramp(f, at, 5.0))
            phone_tracks["ring"].add(lambda f, at=at: ramp(f, at, 5.0) * (0.8 + 0.2 * math.cos((f - at) / 6.0)))
        if approve is not None:
            at = approve["frame"]
            phone_tracks["fill"].add(lambda f, at=at: ramp(f, at, 3.0) + 1.5 * decay(f, at, 10.0))
            phone_tracks["ring"].mul(lambda f, at=at: 1.0 if f < at else 1.0 + 1.5 * decay(f, at, 10.0))
            fade = at + 2.2 * fps
            for name in ("screen", "ring", "fill"):
                phone_tracks[name].mul(lambda f, fade=fade: 1.0 - ramp(f, fade, 12.0))
        if stop is not None:
            at = stop["frame"]
            phone_tracks["screen"].add(lambda f, at=at: ramp(f, at, 2.0))
            phone_tracks["stop"].add(lambda f, at=at: ramp(f, at, 2.0) + 1.2 * decay(f, at, 10.0))

    workspace = None
    ws_tracks = {}
    if "workspace" in cast:
        ws = dict(layout["workspace"])
        workspace = props.build_workspace(ws)
        cue = shot["cues"].get("workspace", {"in": 0.0, "seconds": 0.5})
        at = 1 + cue["in"] * fps
        n = cue["seconds"] * fps
        ws_tracks["edges"] = track(workspace.edges, 0.0)
        ws_tracks["edges"].add(lambda f: ramp(f, at, n))
        ws_tracks["fill"] = track(workspace.fill, 0.0)
        ws_tracks["fill"].add(lambda f: ramp(f, at, n))
        ask = next((e for e in events if e["source"] == "agent" and e.get("tool") == "action"), None)
        ws_tracks["target"] = track(workspace.target, 0.0)
        if ask is not None:
            a = ask["frame"]
            ws_tracks["target"].add(lambda f: ramp(f, a, 3.0) * (0.7 + 1.3 * decay(f, a + 3, 16.0)))

    draw = shot["cues"].get("layer_draw")
    reveal = shot["cues"].get("lights", {}).get("reveal", False)
    light_tracks = {}
    if reveal:
        plan = {"rim": (2, 30, 0.14), "key": (26, 52, 0.0), "fill": (38, 40, 0.0), "wash": (30, 50, 0.0)}
        for name, (a, n, floor) in plan.items():
            light_tracks[name] = Track(frames, floor)
            light_tracks[name].add(lambda f, a=a, n=n, floor=floor: (1.0 - floor) * ramp(f, a, n))

    calls = [
        e for e in events if e["source"] == "agent" and e["kind"] == "request" and e.get("tool") in COMMANDS | QUERIES
    ]
    send_track = track(agent.send, 0.25) if agent is not None else None
    if agent is not None:
        for e in calls:
            send_track.add(lambda f, at=e["frame"]: 3.0 * decay(f, at, 9.0))
    resting = list(layout["agent"]["resting"])
    first_call = len(resting)
    pool = len(layout["agent"]["bubbles"]) - first_call
    before = shot.get("calls_before", 0)

    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, frames
    base = shotlib.base_matrix(shot)
    half = (layer.x1 - layer.x0) / 2 if layer is not None else 0.0
    mid = (layer.x1 + layer.x0) / 2 if layer is not None else 0.0
    for frame in range(0, frames + 2):
        joints = shotlib.joints_at(shot, frame)
        arm.pose(joints)
        arm.key(frame)
        poses = urdf.link_poses(robot, joints, base)
        for cable in servo_cables:
            cable.key(poses, frame)
        m = Matrix(shotlib.cube_at(shot, robot, frame))
        cube.location = m.to_translation()
        cube.rotation_quaternion = m.to_quaternion()
        cube.keyframe_insert("location", frame=frame)
        cube.keyframe_insert("rotation_quaternion", frame=frame)
        studio.key_camera(cam, shotlib.camera_at(cam_shot, frame), frame)

        if reveal:
            for name, obj in lights.items():
                obj.data.energy = LIGHT_WATTS[name] * light_tracks[name].values[frame]
                obj.data.keyframe_insert("energy", frame=frame)

        if layer is not None:
            progress = ramp(frame, 1 + draw["at"] * fps, draw["seconds"] * fps) if draw else 1.0
            layer.key_draw(progress, frame)
            for name, cable in cables.items():
                reach = abs(port_x[name] - mid) / max(half, 1e-6)
                shown = ramp(frame, 1 + draw["at"] * fps + draw["seconds"] * fps * reach, 14.0) if draw else 1.0
                plug = cable.obj.get("plug_frame")
                if plug is not None:
                    shown = min(shown, ramp(frame, plug, 10.0))
                elif name in DEVICE_PROPS and "devices" in cast and shot["cues"].get("connect"):
                    shown = 0.0
                cable.key_drawn(shown, frame)
                port_obj = layer.ports[name][0]
                port_obj.scale = (max(shown, 1e-3),) * 3
                port_obj.keyframe_insert("scale", frame=frame)
            layer.sheet_glow.key(sheet_track.values[frame] * progress, frame)

        if agent is not None:
            made = [c for c in calls if c["frame"] <= frame]
            stack = resting + [first_call + (before + i) % pool for i in range(-min(before, 4), len(made))]
            slide = ramp(frame, made[-1]["frame"], 5.0) if made else 1.0
            props.key_bubbles(agent, stack, slide, frame)

        lit_on: dict[str, float] = {}
        for p in pulses:
            point, level = p.state(frame)
            if point is None:
                p.obj.scale = (1e-3, 1e-3, 1e-3)
            else:
                p.obj.location = point
                p.obj.scale = (1.0, 1.0, 1.0)
            p.obj.keyframe_insert("location", frame=frame)
            p.obj.keyframe_insert("scale", frame=frame)
            if p.blocked_from is not None and frame >= p.blocked_from + 1:
                level *= 0.09
            p.glow.key(level, frame)
            if p.blocked_from is not None:
                color = p.glow.material.node_tree.nodes["Emission"].inputs["Color"]
                hex_color = props.BLOCKED if frame >= p.blocked_from + 1 else "#fff6fb"
                color.default_value = studio.srgb_to_linear(hex_color)
                color.keyframe_insert("default_value", frame=frame)
            for kind, a, b, data in p.steps:
                if kind == "move" and data[2] is not None and a <= frame <= b + TRAIL_M / speed * fps * 1.5:
                    lit_on[data[2]] = (frame - a) / max(b - a, 1e-6)
        for name, cable in cables.items():
            if name in lit_on:
                s = lit_on[name]
                trail = TRAIL_M / cable.path.length
                reverse = any(
                    kind == "move" and data[2] == name and data[1]
                    for p in pulses
                    for kind, a, b, data in p.steps
                    if a <= frame <= b + TRAIL_M / speed * fps * 1.5
                )
                if reverse:
                    a_, b_ = 1.0 - s, 1.0 - s + trail
                else:
                    a_, b_ = s - trail, s
                cable.trail.data.bevel_factor_start = min(max(a_, 0.0), 1.0)
                cable.trail.data.bevel_factor_end = min(max(b_, 0.0), 1.0)
            else:
                cable.trail.data.bevel_factor_start = 0.0
                cable.trail.data.bevel_factor_end = 0.0
            cable.trail.data.keyframe_insert("bevel_factor_start", frame=frame)
            cable.trail.data.keyframe_insert("bevel_factor_end", frame=frame)

        for target, t in tracks:
            if layer is None or target is not layer.sheet_glow:
                target.key(t.values[frame], frame)

    if reveal:
        w = scene.world.node_tree.nodes
        bg = next(n for n in w if n.type == "BACKGROUND" and n.inputs["Color"].is_linked)
        strength = bg.inputs["Strength"].default_value
        for frame in range(0, frames + 2):
            bg.inputs["Strength"].default_value = strength * ramp(frame, 30, 50)
            bg.inputs["Strength"].keyframe_insert("default_value", frame=frame)


def main() -> int:
    """Build, then render the requested frames one by one with timings."""
    opts = args()
    shot, edit = load(opts.shot)
    build(shot, edit, opts.aspect, opts.engine, opts.edge_bevel)
    studio.render_settings(opts.engine, opts.width, opts.height, opts.samples, shot["fps"])
    out = Path(opts.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if opts.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
    scene = bpy.context.scene
    times = out / "times.csv"
    if not times.exists():
        times.write_text("shot,aspect,engine,width,height,samples,frame,seconds\n")
    frames = parse_frames(opts.frames, shot["frames"]) if opts.frames else list(range(1, shot["frames"] + 1))
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(out / f"frame_{frame:04d}.png")
        start = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        seconds = time.perf_counter() - start
        with times.open("a") as handle:
            handle.write(
                f"{opts.shot},{opts.aspect},{opts.engine},{opts.width},{opts.height},{opts.samples},{frame},{seconds:.2f}\n"
            )
        print(f"frame {frame} {seconds:.2f} s", flush=True)
    return 0


if __name__ == "__main__":
    main()
