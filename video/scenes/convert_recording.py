"""Write the film's shot files and its edit from the hub recording and film.json.

Each shot in film.json names a recorded beat, a start time on the recording clock, a length
on screen and one speed for the whole shot. Frame f of the shot shows recording time

    t = t_start + (f - 1) / fps * speed

and the converter samples the 120 Hz rows there, so every joint angle, gripper opening and
cube pose on screen is the recorded one. Keys go into the shot format of shot.py, one key per
frame with linear easing, the gripper in degrees mapped from its recorded percent with 0
percent at the closed end, and the cube as recorded poses in place of the attach rule.

Every hub message inside a shot becomes an event at its fractional frame, and each label in
film.json is tied to the message that triggers it, so a label appears on the frame the hub
or the person did the thing it names.

    python3 -I video/scenes/convert_recording.py
"""

from __future__ import annotations

import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recording
import so101_urdf as urdf

SCENES = Path(__file__).resolve().parent
VIDEO = SCENES.parent
PLAN = SCENES / "film.json"
OUT = SCENES / "shots" / "film"
DEVICE_FILE = VIDEO / "hub" / "so101-sim.hal.yaml"
SCENE_XML = VIDEO / "hub" / "scene.xml"
DEVICES = {"printer": "printer", "plant-waterer": "board", "bench-psu": "psu", "arm": "arm"}
TOOLS = {"action", "write", "read_many", "list_devices", "wait_until", "get_confirmation_status", "hub_status"}


def workspace_box() -> dict[str, list[float]]:
    """The move_to argument limits from the device file, in meters."""
    text = DEVICE_FILE.read_text()
    block = text[text.index("move_to:") :]
    block = block[block.index("args:") : block.index("map:")]
    lo, hi = [], []
    for axis in "xyz":
        match = re.search(rf"\b{axis}: \{{ unit: mm, min: (-?[\d.]+), max: (-?[\d.]+) \}}", block)
        if match is None:
            raise SystemExit(f"no {axis} limit for move_to in {DEVICE_FILE}")
        lo.append(float(match.group(1)) / 1000.0)
        hi.append(float(match.group(2)) / 1000.0)
    return {"min": lo, "max": hi}


def bin_spec() -> dict[str, Any]:
    """The bin's center, inside, wall, height and floor from the recorded scene."""
    root = ET.parse(SCENE_XML).getroot()  # noqa: S314
    body = next(b for b in root.iter("body") if b.get("name") == "bin")
    x, y, _ = (float(v) for v in body.get("pos", "0 0 0").split())
    geoms = {g.get("name"): g for g in body.iter("geom")}
    north = geoms["bin_wall_north"]
    half = [float(v) for v in north.get("size", "").split()]
    wall_y = float(north.get("pos", "").split()[1])
    floor = [float(v) for v in geoms["bin_floor"].get("size", "").split()]
    wall = 2 * half[1]
    return {
        "center": [x, y],
        "inside": round(2 * (wall_y - half[1]), 6),
        "wall": wall,
        "height": 2 * half[2],
        "floor": 2 * floor[2],
    }


def _result(message: dict[str, Any]) -> dict[str, Any]:
    result = message.get("result")
    return result if isinstance(result, dict) else {}


def matches(message: dict[str, Any], when: dict[str, Any]) -> bool:
    """Whether a message fits a label's trigger."""
    for key, want in when.items():
        if key in ("source", "kind", "tool", "path", "via"):
            if message.get(key) != want:
                return False
        elif key == "path_suffix":
            if not str(message.get("path", "")).endswith(want):
                return False
        elif key == "status":
            if _result(message).get("status") != want:
                return False
        elif key == "error":
            error = _result(message).get("error") or {}
            if error.get("name") != want:
                return False
        else:
            raise SystemExit(f"unknown label trigger {key}")
    return True


def event(message: dict[str, Any], frame: float) -> dict[str, Any] | None:
    """A compact event for the scenes and the sound, or None for messages no prop shows."""
    out: dict[str, Any] = {"frame": round(frame, 3), "t": message["t"], "source": message["source"]}
    out["via"] = message["via"]
    out["kind"] = message["kind"]
    if message["via"] == "live":
        body = message.get("event", {})
        if body.get("type") != "audit":
            return None
        out["audit"] = body.get("event")
        out["device"] = DEVICES.get(body.get("device") or "", body.get("device"))
        out["target"] = body.get("target")
        out["status"] = body.get("status")
        out["code"] = body.get("code")
        return out
    if message["via"] == "rest":
        out["path"] = message.get("path")
        return out
    tool = message.get("tool")
    if tool not in TOOLS:
        return None
    out["tool"] = tool
    if message["kind"] == "request":
        args = message.get("arguments") or {}
        out["device"] = DEVICES.get(args.get("device") or "", args.get("device"))
        out["action"] = args.get("action") or args.get("channel")
        out["args"] = args.get("args")
    else:
        result = _result(message)
        out["status"] = result.get("status")
        out["code"] = result.get("code")
        error = result.get("error") or {}
        out["error"] = error.get("name")
        out["device"] = DEVICES.get(result.get("device") or "", result.get("device"))
    return out


def _point(spec: Any, poses: dict[str, urdf.Mat4]) -> list[float]:
    if isinstance(spec, list) and spec and spec[0] == "link":
        _, link, local, *rest = spec
        m = poses[link]
        p = [sum(m[i][k] * local[k] for k in range(3)) + m[i][3] for i in range(3)]
        if rest:
            p = [a + b for a, b in zip(p, rest[0], strict=True)]
        return [round(v, 5) for v in p]
    return [float(v) for v in spec]


def camera_keys(keys: list[dict[str, Any]], frames: int, poses: dict[str, urdf.Mat4], end: float | None) -> list:
    """Camera keys at shot frames, with link-relative points resolved on the shot's first frame."""
    last = end if end is not None else float(frames)
    out = []
    for key in keys:
        frame = 1.0 + key["at"] * (last - 1.0)
        out.append(
            {
                "frame": round(frame, 3),
                "position": _point(key["position"], poses),
                "target": _point(key["target"], poses),
                "focus": _point(key["focus"], poses),
                "lens_mm": key["lens_mm"],
                "fstop": key["fstop"],
            }
        )
    return out


def first(messages: list[dict[str, Any]], when: dict[str, Any], after: float = -math.inf) -> dict[str, Any] | None:
    """The first message at or after `after` that fits a trigger."""
    return next((m for m in messages if m["t"] >= after and matches(m, when)), None)


def build_shot(spec: dict[str, Any], plan: dict[str, Any], rec: recording.Recording, robot: urdf.Robot) -> dict:
    """One shot file."""
    fps = plan["fps"]
    frames = round(spec["seconds"] * fps)
    speed = spec["speed"]
    t0 = spec["t_start"]
    t1 = t0 + (frames - 1) / fps * speed

    def time_of(frame: float) -> float:
        return t0 + (frame - 1.0) / fps * speed

    def frame_of(t: float) -> float:
        return 1.0 + (t - t0) / speed * fps

    beat = rec.beat(spec["beat"])
    arm_keys, cube_keys = [], []
    for frame in range(0, frames + 2):
        t = time_of(frame)
        joints = rec.joints_at(t)
        arm_keys.append({"frame": frame, "joints": {k: round(v, 4) for k, v in joints.items()}, "ease": "linear"})
        position, quat = rec.cube_at(t)
        cube_keys.append(
            {"frame": frame, "position": [round(v, 6) for v in position], "quaternion": [round(v, 6) for v in quat]}
        )
    first_joints = {k: math.radians(v) for k, v in rec.joints_at(t0).items()}
    poses = urdf.link_poses(robot, first_joints)
    messages = rec.messages(time_of(-1), time_of(frames + 1))
    events = [e for m in messages if (e := event(m, frame_of(m["t"]))) is not None]
    for mark in beat.marks:
        if time_of(-1) <= mark["t"] <= time_of(frames + 1):
            events.append(
                {"frame": round(frame_of(mark["t"]), 3), "t": mark["t"], "source": "mark", "text": mark["text"]}
            )
    events.sort(key=lambda e: e["t"])
    calls_before = sum(
        1
        for m in rec.messages(0.0, t0 - 1e-9)
        if m["source"] == "agent" and m["kind"] == "request" and m.get("tool") in TOOLS
    )
    freeze = None
    if "freeze_camera_at" in spec:
        hit = first(messages, spec["freeze_camera_at"]["when"])
        freeze = frame_of(hit["t"]) if hit else None
    labels = []
    for label in spec.get("labels", []):
        hit = first(messages, label["when"])
        if hit is None:
            raise SystemExit(f"{spec['id']}: no message fits the {label['text']} label")
        start = frame_of(hit["t"])
        if "hold_s" in label:
            end = start + label["hold_s"] * fps
        elif "until_when" in label:
            stop = first(messages, label["until_when"], after=hit["t"])
            end = frame_of(stop["t"]) if stop else frames + 1.0
        else:
            end = frames + 1.0
        labels.append(
            {
                "text": label["text"],
                "style": label["style"],
                "from": round(start, 3),
                "to": round(end, 3),
                "t": hit["t"],
                "place": label["place"],
            }
        )
    resolution = plan["resolution"]["landscape"]
    return {
        "name": spec["id"],
        "note": f"Recorded hub motion, beat {beat.name}, {t0:.4f} to {t1:.4f} s at {speed}x.",
        "fps": fps,
        "frames": frames,
        "resolution": resolution,
        "source": {"beat": beat.name, "file": beat.file, "t_start": t0, "t_end": round(t1, 5), "speed": speed},
        "arm": {"base": [0.0, 0.0, 0.0], "yaw_deg": 0.0, "keys": arm_keys},
        "cube": {"size": rec.session["scene"]["cube"]["size_m"], "keys": cube_keys},
        "camera": {"sensor_mm": 36.0, "keys": camera_keys(spec["camera"]["landscape"], frames, poses, freeze)},
        "camera_vertical": {"sensor_mm": 36.0, "keys": camera_keys(spec["camera"]["vertical"], frames, poses, freeze)},
        "set": spec["set"],
        "cues": {k: spec[k] for k in ("lights", "layer_draw", "workspace", "connect", "wordmark") if k in spec},
        "calls_before": calls_before,
        "events": events,
        "labels": labels,
    }


def verify(shot: dict[str, Any], rec: recording.Recording) -> str:
    """Re-read a written shot against the recording, and report how far the arm moves in it."""
    src = shot["source"]
    fps = shot["fps"]
    worst = 0.0
    for key in shot["arm"]["keys"]:
        t = src["t_start"] + (key["frame"] - 1) / fps * src["speed"]
        recorded = rec.joints_at(t)
        worst = max(worst, max(abs(key["joints"][k] - recorded[k]) for k in recorded))
    if worst > 0.001:
        raise SystemExit(f"{shot['name']} keys are {worst:.4f} deg from the recording")
    keys = shot["arm"]["keys"]

    def travel(first: float, last: float) -> float:
        inside = [k for k in keys if first <= k["frame"] <= last]
        return max(abs(k["joints"][n] - inside[0]["joints"][n]) for k in inside for n in k["joints"]) if inside else 0.0

    note = f"keys match the recording within {worst:.4f} deg, arm travel {travel(1, shot['frames']):.2f} deg"
    stop = next((e for e in shot["events"] if e.get("audit") == "safe_state" and e.get("device") == "arm"), None)
    if stop is not None:
        note += f", after the arm's safe state {travel(stop['frame'] + 1, shot['frames']):.4f} deg"
    return note


def main() -> int:
    """Write shots/film/<id>.json for every shot and shots/film/edit.json for the whole film."""
    plan = json.loads(PLAN.read_text())
    rec = recording.load()
    robot = urdf.load()
    OUT.mkdir(parents=True, exist_ok=True)
    fps = plan["fps"]
    layout = dict(plan["layout"])
    layout["bin"] = bin_spec()
    limit = first(rec.beat("limit").messages, {"source": "agent", "kind": "request", "tool": "action"})
    args = limit["arguments"]["args"]
    layout["workspace"] = {**workspace_box(), "target": [args[a]["value"] / 1000.0 for a in "xyz"]}
    layout["cube_size"] = rec.session["scene"]["cube"]["size_m"]
    edit: dict[str, Any] = {"fps": fps, "resolution": plan["resolution"], "layout": layout, "items": [], "labels": []}
    start = 0
    for spec in plan["shots"]:
        shot = build_shot(spec, plan, rec, robot)
        path = OUT / f"{spec['id']}.json"
        path.write_text(json.dumps(shot, separators=(",", ":")) + "\n")
        item = {
            "kind": "shot",
            "id": spec["id"],
            "storyboard": spec["storyboard"],
            "start": start,
            "frames": shot["frames"],
            "source": shot["source"],
        }
        if "wordmark" in spec:
            item["wordmark"] = round(spec["wordmark"]["at"] * fps)
        edit["items"].append(item)
        for label in shot["labels"]:
            edit["labels"].append(
                {
                    **label,
                    "shot": spec["id"],
                    "from": round(start + label["from"] - 1),
                    "to": round(start + label["to"] - 1),
                }
            )
        start += shot["frames"]
        if "after_black_s" in spec:
            black = round(spec["after_black_s"] * fps)
            edit["items"].append({"kind": "black", "id": f"{spec['id']}-black", "start": start, "frames": black})
            start += black
        print(
            f"{spec['id']:12s} {shot['frames']:4d} frames  beat {shot['source']['beat']:15s} "
            f"{shot['source']['t_start']:8.4f} to {shot['source']['t_end']:8.4f} s at {spec['speed']}x, "
            f"{verify(shot, rec)}"
        )
    card = plan["end_card"]
    frames = round(card["seconds"] * fps)
    edit["items"].append({"kind": "card", "id": "s8-end", "storyboard": 8, "start": start, "frames": frames, **card})
    start += frames
    for label in edit["labels"]:
        label["to"] = min(label["to"], start)
    edit["frames"] = start
    (OUT / "edit.json").write_text(json.dumps(edit, indent=1) + "\n")
    print(f"film {start} frames, {start / fps:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
