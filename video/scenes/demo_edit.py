"""Cut the OpenHAL demo video from one recorded take, and write its edit and its cue sheet.

    .venv/bin/python video/scenes/demo_edit.py --take take-4

Every line in a terminal scene is a line Claude Code received in the take, quoted as received and
shortened only where Claude Code itself cuts a long call or result. Every arm pose, cube pose and
joint speed is sampled from the take's frames at the take time a video frame shows, at 1x. Every
Inspector click lands on the frame of its recorded click. The terminal scenes show the real time
that passed on Claude Code's own timer where the edit skips a wait.

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
from demo_lines import FPS, Script, audit, clip, find, frame_in, history, motion_start, result_of, result_spans
from demo_take import Take

VIDEO = Path(__file__).resolve().parent.parent
OUT = VIDEO / "remotion" / "src" / "demo"
SPEED_LIMIT = 60.0
HUB = {"product": "OpenHAL 0.1.0", "protocol": "0.1", "conformance": "full"}
DEVICE = {"name": "SO-101 arm (simulated)", "id": "arm", "driver": "mujoco", "conformance": "full", "hazard": "medium"}
DEVICE_FILE = "arm.hal.yaml"
CAMERAS = {
    "pick": {
        "from": {"position": [0.44, -0.84, 0.56], "target": [0.12, -0.02, 0.13], "fov": 30},
        "to": {"position": [0.41, -0.78, 0.52], "target": [0.13, -0.01, 0.12], "fov": 30},
    },
    "drop": {
        "from": {"position": [0.4, -0.82, 0.52], "target": [0.12, -0.07, 0.1], "fov": 30},
        "to": {"position": [0.37, -0.76, 0.48], "target": [0.12, -0.08, 0.1], "fov": 30},
    },
    "grip": {
        "from": {"position": [0.54, -0.56, 0.4], "target": [0.16, 0.04, 0.11], "fov": 28},
        "to": {"position": [0.51, -0.52, 0.38], "target": [0.16, 0.04, 0.12], "fov": 28},
    },
    "wide": {
        "from": {"position": [0.42, -0.84, 0.54], "target": [0.12, -0.04, 0.1], "fov": 30},
        "to": {"position": [0.4, -0.8, 0.51], "target": [0.12, -0.04, 0.1], "fov": 30},
    },
}
HELD_WHY = (
    "arm.hal.yaml requires a person to confirm drop_in_bin each time. Nothing reaches the device until you approve."
)
"""The Inspector's reason for the held request, as its screenshot in take-4/inspector/1-pending-dark.png reads."""
DEVICE_YAML = VIDEO / "hub" / "so101-demo.hal.yaml"
MODELS = {"claude-opus-5-5": "Opus 5.5"}
ROOT = VIDEO.parent
DEVICE_FILES = [
    "examples/print-babysitter/printer.hal.yaml",
    "openhal/drivers/esphome/examples/plant-waterer.hal.yaml",
    "openhal/drivers/scpi/examples/rigol-dp832.hal.yaml",
]
STATS_FILE = VIDEO / "data" / "STATS.md"
STATS: list[dict] = [
    {"value": 5.5, "decimals": 1, "unit": "ms", "label": "added to check a request"},
    {"value": 34, "decimals": 0, "unit": "drivers", "label": "for real hardware"},
]
STATS_SOURCE = "Median of 1,200 requests to the simulated arm on a 2018 MacBook Pro"


def action_description(action: str) -> str:
    """An action's description from the take's device file, which the Inspector shows."""
    import yaml

    return yaml.safe_load(DEVICE_YAML.read_text(encoding="utf-8"))["actions"][action]["description"]


def device_cards() -> list[dict]:
    """A card for each example device file, with the file's own name, model and hazard."""
    import yaml

    cards = []
    for path in DEVICE_FILES:
        text = (ROOT / path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        device = data["device"]
        hazard = next(line for line in text.splitlines() if line.startswith("hazard:"))
        if isinstance(device, dict):
            cards.append(
                {
                    "name": device["name"],
                    "file": Path(path).name,
                    "lines": [f"{device['manufacturer']} {device['model']}", hazard],
                }
            )
        else:
            driver = next(iter(data["connect"]))
            cards.append({"name": device, "file": Path(path).name, "lines": [f"{driver} driver", hazard]})
    return cards


def stats_cards() -> dict | None:
    """The stat cards, from the numbers in video/data/STATS.md, once that file exists."""
    if not STATS_FILE.exists() or not STATS:
        return None
    text = STATS_FILE.read_text(encoding="utf-8")
    for stat in STATS:
        if str(stat["value"]) not in text:
            raise SystemExit(f"{stat['value']} is not in {STATS_FILE}")
    return {"stats": STATS, "source": STATS_SOURCE}


def header(take: Take) -> dict:
    """Claude Code's header from the session's init event, the version and the model."""
    stream = demo_take.jsonl(take.folder / "claude.stream.jsonl")
    init = next(event for event in stream if event.get("type") == "system" and event.get("subtype") == "init")
    return {
        "title": "Claude Code",
        "version": f"v{init['claude_code_version']}",
        "model": MODELS.get(init["model"], init["model"]),
    }


def panel(label: str, value: object, verdict: dict | None, scale: float = 100, **extra: object) -> dict:
    """The data panel beside the arm."""
    return {
        "title": "SO-101 arm",
        "subtitle": DEVICE_FILE,
        "label": label,
        "unit": "deg/s",
        "limit": SPEED_LIMIT,
        "scaleMax": scale,
        "limitLabel": f"{SPEED_LIMIT:.0f} deg/s max",
        "value": value,
        "verdict": verdict,
        **extra,
    }


def build(take: Take) -> tuple[dict, dict]:
    """The edit and the cue sheet."""
    scenes: list[dict] = []
    cues: dict = {
        "fps": FPS,
        "typing": [],
        "calls": [],
        "results": [],
        "presses": [],
        "blocks": [],
        "chimes": [],
        "servos": [],
        "silence": [],
        "sections": [],
    }
    cursor = 0
    hub = {**HUB, "host": f"127.0.0.1:{take.session['hub_port']}"}

    def add(scene: dict, energy: int, chord: str, script: Script | None = None) -> dict:
        nonlocal cursor
        scene["from"] = cursor
        scenes.append(scene)
        cues["sections"].append(
            {
                "start": cursor / FPS,
                "end": (cursor + scene["frames"]) / FPS,
                "energy": energy,
                "chord": chord,
                "id": scene["id"],
            }
        )
        if script:
            for a, b, chars in script.typing:
                cues["typing"].append({"start": (cursor + a) / FPS, "end": (cursor + b) / FPS, "chars": chars})
            cues["calls"].extend((cursor + f) / FPS for f in script.calls)
            cues["results"].extend((cursor + f) / FPS for f in script.results)
        cursor += scene["frames"]
        return scene

    def desk(
        scene_id: str,
        start: float,
        frames: int,
        camera: str,
        spec: dict,
        energy: int,
        chord: str,
        stop: dict | None = None,
        servo: int | None = None,
    ) -> tuple[dict, float]:
        poses, speeds, t0 = clip(take, start, frames)
        scene = {
            "id": scene_id,
            "kind": "desk",
            "frames": frames,
            "poses": poses,
            "speeds": speeds,
            "camera": {**CAMERAS[camera], "frames": frames},
            "panel": spec,
        }
        if stop:
            scene["stop"] = stop
        add(scene, energy, chord)
        cues["servos"].append(
            {
                "start": scene["from"] / FPS,
                "limit": SPEED_LIMIT,
                "speeds": speeds[: servo if servo is not None else frames],
            }
        )
        return scene, t0

    ask = find(take, "prompt")
    listing = find(take, "tool", after=ask.t, tool="list_devices")
    describe = find(take, "tool", after=ask.t, tool="describe_device")
    check = find(take, "tool", after=ask.t, tool="plan_check")
    because = find(take, "text", after=check.t)
    steps = find(take, "tool", after=ask.t, tool="run_steps")
    steps_done = result_of(take, steps)

    one = Script(take.mark("prompt sent", 0)["t_sent"], history(take, ask.t))
    one.prompt(ask, at=10, cps=34)
    one.wait(listing.t, 14)
    one.call(take, listing, gap=7, after=6)
    one.wait(describe.t, 8)
    one.call(take, describe, gap=7, after=6)
    one.wait(check.t, 16)
    one.call(take, check, gap=10, after=10)
    one.text(because, 28)
    one.wait(steps.t, 8)
    one.call(take, steps, result=False, after=6, brand=True)
    one.wait(steps.t + 18 / FPS, 18)
    first = one.scene("ask")
    add(first, 2, "a", one)

    move = motion_start(take, steps.t)
    lowered = audit(take, "action", after=move + 1.0, target="action:move_to", status="done")
    lowered = audit(take, "action", after=lowered["t"] + 0.01, target="action:move_to", status="done")
    closing = audit(take, "write", after=lowered["t"], target="write:gripper_goal", status="done")
    shot_a = (move - 0.15, lowered["t"] + 0.12)
    shot_b = (closing["t"] - 0.1, steps_done.t + 0.4)
    frames_a = round((shot_a[1] - shot_a[0]) * FPS)
    frames_b = round((shot_b[1] - shot_b[0]) * FPS)
    poses_a, speeds_a, _ = clip(take, shot_a[0], frames_a)
    poses_b, speeds_b, _ = clip(take, shot_b[0], frames_b)
    pick = add(
        {
            "id": "pick",
            "kind": "desk",
            "frames": frames_a + frames_b,
            "poses": poses_a + poses_b,
            "speeds": speeds_a + speeds_b,
            "camera": {**CAMERAS["pick"], "frames": frames_a},
            "shots": [{"start": frames_a, "camera": {**CAMERAS["grip"], "frames": frames_b}}],
            "panel": panel(
                "Fastest joint",
                "speed",
                {"text": "done", "tone": "ok", "at": frames_a + frame_in(shot_b[0], steps_done.t)},
            ),
            "skipped": [round(shot_a[1], 3), round(shot_b[0], 3)],
        },
        4,
        "f",
    )
    cues["servos"].append({"start": pick["from"] / FPS, "limit": SPEED_LIMIT, "speeds": speeds_a + speeds_b})

    lifted = find(take, "text", after=steps_done.t)
    drop = find(take, "tool", after=steps_done.t, tool="action")
    two = Script(take.mark("prompt sent", 0)["t_sent"], history(take, steps_done.t + 0.001))
    two.last = steps_done.t
    two.wait(lifted.t, 8)
    two.text(lifted, 24)
    two.call(take, drop, gap=14, after=40, brand=True)
    add(two.scene("held"), 3, "c", two)

    held = take.mark("request held for a person", 0)
    click = take.mark("Approve clicked in the Inspector", 0)["t_click"]
    press = 64
    shown_from = click - press / FPS
    approve = add(
        {
            "id": "approve",
            "kind": "inspector",
            "frames": press + 14,
            "hub": hub,
            "device": DEVICE,
            "request": {
                "agent": "claude",
                "principal": "agent:claude",
                "action": "drop_in_bin",
                "deviceName": DEVICE["name"],
                "requestId": held["request_id"],
                "requested": f"{round(shown_from - held['t'])} s ago",
                "method": "hal/action",
                "params": '{ "device": "arm", "action": "drop_in_bin", "args": {} }',
                "does": action_description("drop_in_bin"),
                "why": HELD_WHY,
                "expires": round(300 - (shown_from - held["t"])),
            },
            "cursor": [
                {"at": 0, "x": 1180, "y": 660},
                {"at": 8, "x": 1180, "y": 660},
                {"at": press - 14, "x": 1010, "y": 398},
            ],
            "press": press,
            "zoom": {"from": 1.0, "to": 1.32, "origin": [1060, 420]},
        },
        2,
        "d",
    )
    cues["presses"].append((approve["from"] + press) / FPS)

    drop_done = audit(take, "action", after=click, target="action:drop_in_bin", status="done")
    drop_scene, _ = desk(
        "drop",
        click,
        round((drop_done["t"] - click) * FPS) + 24,
        "drop",
        panel("Fastest joint", "speed", {"text": "done", "tone": "ok", "at": frame_in(click, drop_done["t"])}),
        4,
        "c",
    )
    cues["chimes"].append((drop_scene["from"] + frame_in(click, drop_done["t"])) / FPS)

    again = find(take, "prompt", after=drop_done["t"])
    reading = find(take, "tool", after=again.t, tool="read_many")
    status = find(take, "tool", after=again.t, tool="get_confirmation_status")
    plan = find(take, "text", after=again.t)
    fast = find(take, "tool", after=again.t, tool="run_steps")
    refused = find(take, "text", after=fast.t)
    three = Script(take.mark("prompt sent", 1)["t_sent"], history(take, again.t))
    three.prompt(again, at=8, cps=48)
    three.wait(reading.t, 10)
    three.call(take, reading, result=False, after=4)
    three.call(take, status, result=False, after=4)
    reading_result, status_result = result_of(take, reading), result_of(take, status)
    three.blocks[-2]["result"] = {"spans": result_spans(reading_result.result), "at": three.frame + 2}
    three.blocks[-1]["result"] = {"spans": result_spans(status_result.result), "at": three.frame + 4}
    three.results.extend([three.frame + 2, three.frame + 4])
    three.frame += 10
    three.last = status_result.t
    three.wait(plan.t, 8)
    three.text(plan, 20)
    three.wait(fast.t, 10)
    three.call(take, fast, gap=14, after=34, brand=True, limit=190)
    three.wait(refused.t, 10)
    three.text(refused, 46)
    limit_scene = add(three.scene("limit"), 3, "g", three)
    blocked_at = (limit_scene["from"] + three.results[-1]) / FPS
    cues["blocks"].append(blocked_at)

    error = json.loads(result_of(take, fast).result)["error"]
    requested = next(
        step["args"]["speed"]["value"]
        for step in fast.args["steps"]
        if step.get("kind") == "action" and "speed" in step.get("args", {})
    )
    block_frames = 96
    still = desk(
        "refused",
        result_of(take, fast).t - 0.5,
        block_frames,
        "wide",
        panel(
            "Requested speed",
            requested,
            {"text": error["name"], "tone": "blocked", "at": 40},
            scale=140,
            countFrom=0,
            countFrames=26,
        ),
        1,
        "g",
    )[0]
    cues["blocks"].append((still["from"] + 36) / FPS)

    last = find(take, "prompt", after=fast.t)
    run = find(take, "tool", after=last.t, tool="run_steps")
    four = Script(take.mark("prompt sent", 2)["t_sent"], history(take, last.t))
    four.prompt(last, at=6, cps=36)
    four.wait(run.t, 14)
    four.call(take, run, result=False, after=16, brand=True)
    add(four.scene("normal"), 3, "a", four)

    stop_click = take.mark("STOP clicked in the Inspector")["t_click"]
    stop_entry = audit(take, "stop", after=last.t)
    opening = audit(take, "write", after=run.t, target="write:gripper_goal", status="done")
    stop_start = opening["t"] - 0.1
    stop_frames = round((stop_click - stop_start) * FPS) + 54
    press = round((stop_click - stop_start) * FPS)
    stop_scene, _ = desk(
        "stop",
        stop_start,
        stop_frames,
        "wide",
        panel(
            "Fastest joint",
            "speed",
            {"text": "stopped", "tone": "blocked", "at": frame_in(stop_start, stop_entry["t"])},
        ),
        4,
        "a",
        stop={
            "hub": hub,
            "reason": stop_entry["details"]["reason"],
            "press": press,
            "cursor": [{"at": 0, "x": 960, "y": 330}, {"at": max(1, press - 18), "x": 1186, "y": 40}],
        },
        servo=press,
    )
    cues["presses"].append((stop_scene["from"] + press) / FPS)
    cues["silence"].append(
        {"start": (stop_scene["from"] + press) / FPS, "end": (stop_scene["from"] + stop_frames) / FPS}
    )

    stats = stats_cards()
    if stats:
        add({"id": "stats", "kind": "stats", "frames": 105, "stats": stats["stats"], "source": stats["source"]}, 4, "f")
    add(
        {
            "id": "devices",
            "kind": "devices",
            "frames": 105,
            "title": "The same hub works with other hardware.",
            "devices": device_cards(),
        },
        4,
        "a",
    )
    add(
        {
            "id": "end",
            "kind": "end",
            "frames": 132,
            "tagline": "An open-source protocol for AI agents to control hardware.",
            "command": "uvx halkit demo",
            "url": "sohan-bhat.github.io/OpenHAL",
            "finePrint": "Simulated arm. Real OpenHAL hub. Not affiliated with Anthropic.",
        },
        2,
        "a",
    )

    edit = {
        "take": take.name,
        "fps": FPS,
        "frames": cursor,
        "header": header(take),
        "scenes": scenes,
    }
    cues["duration"] = cursor / FPS
    return edit, cues


def main() -> int:
    """Write the edit and the cue sheet."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--take", default="take-3")
    args = parser.parse_args()
    take = demo_take.load(args.take)
    edit, cues = build(take)
    (OUT / "edit.json").write_text(json.dumps(edit, separators=(",", ":")) + "\n", encoding="utf-8")
    (OUT / "cues.json").write_text(json.dumps(cues, separators=(",", ":")) + "\n", encoding="utf-8")
    for scene in edit["scenes"]:
        last = scene["from"] + scene["frames"] - 1
        print(f"{scene['id']:8} {scene['kind']:9} frames {scene['from']:4} to {last:4}, {scene['frames'] / FPS:5.2f} s")
    print(f"{edit['frames']} frames, {edit['frames'] / FPS:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
