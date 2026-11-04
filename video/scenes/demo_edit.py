"""Cut the OpenHAL demo video from one recorded take, and write its edit and its cue sheet.

    .venv/bin/python video/scenes/demo_edit.py --take take-4

The video is built around the 3D desk. Claude Code shows only as a slim prompt line at the bottom,
with the real prompt typing out and Claude Code's working timer counting the real seconds that
passed. Each request travels to the arm through the hub's pink layer as a short pulse named with
the real tool, waits at the layer as pending until the recorded Approve click, stops at the layer
on LIMIT_EXCEEDED, and STOP freezes everything on the recorded click frame. Every arm pose, cube
pose and joint speed is sampled from the take on the hub's clock at 1x.

The script writes video/remotion/src/demo/edit.json for Remotion and
video/remotion/src/demo/cues.json for demo_sound.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_take
from demo_lines import FPS, audit, find, motion_start, result_of
from demo_take import Take

VIDEO = Path(__file__).resolve().parent.parent
OUT = VIDEO / "remotion" / "src" / "demo"
CPS = 34
REQUESTED_SWEEP = 60.0
"""Degrees the wedge spans, how far the shoulder may turn in one second at the device file's 60 deg/s."""
DEVICE_FILES = [
    "examples/print-babysitter/printer.hal.yaml",
    "openhal/drivers/esphome/examples/plant-waterer.hal.yaml",
    "openhal/drivers/scpi/examples/rigol-dp832.hal.yaml",
]
STATS = [
    {"value": 5.5, "decimals": 1, "unit": "ms", "label": "added to check a request"},
    {"value": 34, "decimals": 0, "unit": "drivers"},
]
STATS_FILE = VIDEO / "data" / "STATS.md"


def cam(position: list[float], target: list[float], fov: float) -> dict:
    """One camera pose, z up, metres."""
    return {"position": position, "target": target, "fov": fov}


def move(start: dict, end: dict, frames: int) -> dict:
    """A slow eased move between two camera poses."""
    return {"from": start, "to": end, "frames": frames}


CAMERAS = {
    "establish": (cam([0.62, -0.9, 0.46], [0.08, -0.08, 0.1], 30), cam([0.52, -0.78, 0.4], [0.08, -0.07, 0.1], 30)),
    "shoulder": (cam([0.3, -0.36, 0.2], [0.0, 0.0, 0.11], 30), cam([0.24, -0.29, 0.17], [0.0, 0.0, 0.11], 28)),
    "reach": (cam([0.5, -0.62, 0.34], [0.12, 0.02, 0.07], 30), cam([0.46, -0.56, 0.31], [0.13, 0.03, 0.07], 30)),
    "gripper": (cam([0.42, -0.2, 0.16], [0.2, 0.09, 0.07], 34), cam([0.39, -0.17, 0.15], [0.2, 0.09, 0.08], 33)),
    "held": (cam([0.58, -0.86, 0.42], [0.06, -0.1, 0.13], 30), cam([0.53, -0.8, 0.39], [0.06, -0.1, 0.13], 30)),
    "bin": (cam([0.42, -0.58, 0.07], [0.11, -0.15, 0.12], 36), cam([0.38, -0.53, 0.075], [0.11, -0.15, 0.12], 36)),
    "wedge": (cam([0.3, -0.66, 0.66], [0.05, -0.06, 0.04], 34), cam([0.27, -0.6, 0.6], [0.05, -0.06, 0.05], 33)),
    "stop": (cam([0.58, -0.86, 0.42], [0.06, -0.08, 0.12], 30), cam([0.52, -0.78, 0.38], [0.06, -0.08, 0.12], 30)),
}


def shot(name: str, start: int, frames: int) -> dict:
    """A named camera move starting at a scene frame."""
    a, b = CAMERAS[name]
    return {"start": start, "camera": move(a, b, frames)}


def sample(take: Take, times: list[float]) -> tuple[list[list[float]], list[float]]:
    """Poses and the fastest joint speed at each take time."""
    return [take.pose(t) for t in times], [round(take.speed(t), 2) for t in times]


def typed_frames(text: str, cps: int = CPS) -> int:
    """Frames the prompt takes to type out."""
    return round(len(text) / cps * FPS)


def build(take: Take) -> tuple[dict, dict]:
    """The edit and the cue sheet."""
    scenes: list[dict] = []
    cues: dict = {"fps": FPS, "typing": [], "clicks": [], "switches": [], "servos": [], "music": []}
    cursor = 0

    def add(scene: dict) -> dict:
        nonlocal cursor
        scene["from"] = cursor
        scenes.append(scene)
        cursor += scene["frames"]
        return scene

    def absolute(scene: dict, frame: int) -> float:
        return (scene["from"] + frame) / FPS

    def stage(scene_id: str, times: list[float], shots: list[dict], **extra: object) -> dict:
        poses, speeds = sample(take, times)
        scene = add(
            {
                "id": scene_id,
                "kind": "stage",
                "frames": len(times),
                "poses": poses,
                "speeds": speeds,
                "shots": shots,
                **extra,
            }
        )
        cues["servos"].append({"start": scene["from"] / FPS, "speeds": speeds})
        return scene

    sent = [mark["t_sent"] for mark in take.marks if mark.get("text") == "prompt sent"]
    ask = find(take, "prompt")
    steps = find(take, "tool", after=ask.t, tool="run_steps")
    steps_done = result_of(take, steps)

    typing = 12
    submit = typing + typed_frames(ask.text) + 8
    launch = submit + 42
    layer_at = launch + 14
    arrive = layer_at + 16
    frames = arrive + 8
    times = [steps.t + (f - launch) / FPS if f >= launch else steps.t for f in range(frames)]
    one = stage(
        "ask",
        times,
        [shot("establish", 0, frames)],
        prompt={
            "text": ask.text,
            "at": typing,
            "submit": submit,
            "cps": CPS,
            "timer": {"from": 0, "to": round(steps.t - sent[0], 2), "until": launch},
        },
        pulse={"tool": "run_steps", "at": launch, "layerAt": layer_at, "arriveAt": arrive},
    )
    cues["typing"].append({"start": absolute(one, typing), "end": absolute(one, submit - 8), "chars": len(ask.text)})

    move_start = motion_start(take, steps.t)
    lowered = audit(take, "action", after=move_start + 1.0, target="action:move_to", status="done")
    lowered = audit(take, "action", after=lowered["t"] + 0.01, target="action:move_to", status="done")
    closing = audit(take, "write", after=lowered["t"], target="write:gripper_goal", status="done")
    a0 = max(steps.t + (frames - launch) / FPS, move_start - 0.3)
    a1 = lowered["t"] + 0.12
    b0, b1 = closing["t"] - 0.1, steps_done.t + 0.4
    frames_a = round((a1 - a0) * FPS)
    frames_b = round((b1 - b0) * FPS)
    pick_times = [a0 + f / FPS for f in range(frames_a)] + [b0 + f / FPS for f in range(frames_b)]
    pick = stage(
        "pick",
        pick_times,
        [shot("shoulder", 0, 66), shot("reach", 66, frames_a - 66), shot("gripper", frames_a, frames_b)],
    )
    pick["skipped"] = [round(a1, 3), round(b0, 3)]

    drop = find(take, "tool", after=steps_done.t, tool="action")
    pending = result_of(take, drop)
    held = take.mark("request held for a person", 0)
    click = take.mark("Approve clicked in the Inspector", 0)["t_click"]
    launch = 10
    layer_at = launch + round((pending.t - drop.t) * FPS)
    press = layer_at + 78
    frames = press + 22
    held_times = [steps_done.t + 1.0 + f / FPS for f in range(frames)]
    two = stage(
        "held",
        held_times,
        [shot("held", 0, frames)],
        prompt={
            "text": ask.text,
            "at": -1000,
            "submit": 0,
            "cps": CPS,
            "timer": {"from": round(drop.t - sent[0], 2), "to": round(click - sent[0], 2), "until": press},
        },
        pulse={
            "tool": "drop_in_bin",
            "at": launch,
            "layerAt": layer_at,
            "holdUntil": press + 2,
            "arriveAt": press + 18,
        },
        answer={"word": "pending", "tone": "pending", "at": layer_at, "until": press},
        card={
            "kind": "approve",
            "label": "Approve and run drop_in_bin",
            "at": layer_at + 10,
            "press": press,
            "cursor": [
                {"at": 0, "x": -40, "y": 260},
                {"at": press - 34, "x": -40, "y": 260},
                {"at": press - 4, "x": 214, "y": 92},
            ],
        },
    )
    two["request"] = held["request_id"]
    cues["clicks"].append(absolute(two, press))

    drop_done = audit(take, "action", after=click, target="action:drop_in_bin", status="done")
    frames = round((drop_done["t"] + 0.9 - click) * FPS)
    stage("drop", [click + f / FPS for f in range(frames)], [shot("bin", 0, frames)])

    again = find(take, "prompt", after=drop_done["t"])
    fast = find(take, "tool", after=again.t, tool="run_steps")
    blocked = result_of(take, fast)
    error = json.loads(blocked.result)["error"]
    requested = next(
        step["args"]["speed"]["value"]
        for step in fast.args["steps"]
        if step.get("kind") == "action" and "speed" in step.get("args", {})
    )
    first_target = audit(take, "action", after=steps.t, target="action:move_to", status="done")
    typing = 10
    submit = typing + typed_frames(again.text, 44) + 8
    launch = submit + 24
    layer_at = launch + round((blocked.t - fast.t) * FPS)
    frames = layer_at + 66
    still = fast.t
    three = stage(
        "limit",
        [still for _ in range(frames)],
        [shot("wedge", 0, frames)],
        prompt={
            "text": again.text,
            "at": typing,
            "submit": submit,
            "cps": 44,
            "timer": {"from": 0, "to": round(fast.t - sent[1], 2), "until": launch},
        },
        pulse={"tool": "run_steps", "at": launch, "layerAt": layer_at, "blocked": True},
        answer={"word": error["name"], "tone": "blocked", "at": layer_at + 2, "lift": 0.24, "dx": -230},
        limit={
            "at": layer_at + 4,
            "ghostFrom": take.pose(still)[:6],
            "ghostTo": take.pose(first_target["t"])[:6],
            "requested": requested,
            "sweepDeg": REQUESTED_SWEEP,
        },
    )
    three["error"] = {"code": error["code"], "name": error["name"]}
    cues["typing"].append(
        {"start": absolute(three, typing), "end": absolute(three, submit - 8), "chars": len(again.text)}
    )
    cues["switches"].append({"at": absolute(three, layer_at), "level": -14})

    last = find(take, "prompt", after=fast.t)
    run = find(take, "tool", after=last.t, tool="run_steps")
    stop_click = take.mark("STOP clicked in the Inspector")["t_click"]
    stop_entry = audit(take, "stop", after=last.t)
    typing = 8
    submit = typing + typed_frames(last.text) + 8
    launch = submit + 22
    layer_at = launch + 12
    press = launch + round((stop_click - run.t) * FPS)
    frames = press + 56
    four = stage(
        "stop",
        [run.t + (f - launch) / FPS if f >= launch else run.t for f in range(frames)],
        [shot("stop", 0, press)],
        prompt={
            "text": last.text,
            "at": typing,
            "submit": submit,
            "cps": CPS,
            "timer": {"from": 0, "to": round(run.t - sent[2], 2), "until": launch},
        },
        pulse={"tool": "run_steps", "at": launch, "layerAt": layer_at, "arriveAt": layer_at + 14},
        card={
            "kind": "stop",
            "label": "STOP",
            "at": press - 40,
            "press": press,
            "cursor": [
                {"at": 0, "x": -40, "y": 260},
                {"at": press - 30, "x": -40, "y": 260},
                {"at": press - 4, "x": 132, "y": 96},
            ],
        },
        flatAt=press + round((stop_entry["t"] - stop_click) * FPS),
    )
    four["shots"].append(
        {
            "start": press,
            "camera": {"from": four["shots"][0]["camera"]["to"], "to": four["shots"][0]["camera"]["to"], "frames": 1},
        }
    )
    cues["typing"].append({"start": absolute(four, typing), "end": absolute(four, submit - 8), "chars": len(last.text)})
    cues["clicks"].append(absolute(four, press))
    cues["switches"].append({"at": absolute(four, press) + 0.02, "level": -6})
    cues["servos"][-1]["speeds"] = cues["servos"][-1]["speeds"][:press]
    stop_at = absolute(four, press)

    text = STATS_FILE.read_text(encoding="utf-8")
    for stat in STATS:
        if str(stat["value"]) not in text:
            raise SystemExit(f"{stat['value']} is not in {STATS_FILE}")
    stats = add({"id": "stats", "kind": "stats", "frames": 96, "stats": STATS})
    add({"id": "devices", "kind": "devices", "frames": 84, "files": [Path(path).name for path in DEVICE_FILES]})
    add(
        {
            "id": "end",
            "kind": "end",
            "frames": 132,
            "tagline": "An open-source protocol for AI agents to control hardware.",
            "command": "uvx halkit demo",
            "url": "sohan-bhat.github.io/OpenHAL",
            "finePrint": "Simulated arm. Real OpenHAL hub. Not affiliated with Anthropic.",
        }
    )
    for path in DEVICE_FILES:
        if not (VIDEO.parent / path).exists():
            raise SystemExit(f"{path} is missing")

    cues["music"] = [
        {"start": 0.0, "end": stop_at, "offset": 0.0, "fade_in": 1.0},
        {"start": stats["from"] / FPS, "end": cursor / FPS, "offset": MUSIC_RETURN, "fade_in": 0.05, "fade_out": 1.6},
    ]
    cues["duration"] = cursor / FPS
    edit = {"take": take.name, "fps": FPS, "frames": cursor, "scenes": scenes}
    return edit, cues


MUSIC_RETURN = 82.0
"""Seconds into the track where the music comes back after STOP, the bar where the hats enter."""


def main() -> int:
    """Write the edit and the cue sheet."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--take", default="take-4")
    args = parser.parse_args()
    take = demo_take.load(args.take)
    edit, cues = build(take)
    (OUT / "edit.json").write_text(json.dumps(edit, separators=(",", ":")) + "\n", encoding="utf-8")
    (OUT / "cues.json").write_text(json.dumps(cues, separators=(",", ":")) + "\n", encoding="utf-8")
    for scene in edit["scenes"]:
        last = scene["from"] + scene["frames"] - 1
        print(f"{scene['id']:8} {scene['kind']:8} frames {scene['from']:4} to {last:4}, {scene['frames'] / FPS:5.2f} s")
    print(f"{edit['frames']} frames, {edit['frames'] / FPS:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
