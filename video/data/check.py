"""Check the recorded film data in this folder (README.md).

    uv run python video/data/check.py

The checks, each against the stated tolerance.

- Every beat file plays at its fixed frame rate, with no gap or repeat.
- While the hub blocks the move outside the workspace box, no joint moves more than
  STILL_DEG from where it was when the agent sent the move, until the beat ends.
- From the hub's reply to STOP until the beat ends, no joint moves more than STILL_DEG from
  where it was at that reply, and the arm was moving when the person pressed STOP.
- The hub's messages carry the beats, the three connect events, the LIMIT_EXCEEDED block, the
  pending drop and its approval, and the stop.
"""

from __future__ import annotations

import json
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STILL_DEG = 0.05
"""How far any joint may move while the arm counts as still, in degrees."""
MOVING_DEG_S = 5.0
"""How fast at least one joint must turn just before STOP for the stop to count as mid-motion."""
MAX_BYTES = 50 * 1024 * 1024
JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper_jaw")


def load(name: str) -> Any:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def columns(beat: dict[str, Any]) -> list[int]:
    names = beat["frames"]["columns"]
    return [names.index(joint) for joint in JOINTS]


def moved(beat: dict[str, Any], start: float, end: float) -> float:
    """The most any joint moved, in degrees, from the first frame at or after `start` until `end`."""
    rows = [row for row in beat["frames"]["rows"] if start <= row[0] <= end]
    if not rows:
        raise AssertionError(f"no frames between {start} s and {end} s")
    picks = columns(beat)
    first = rows[0]
    return max(abs(row[i] - first[i]) for row in rows for i in picks)


def speed(beat: dict[str, Any], start: float, end: float) -> float:
    """The fastest any joint turned between two times, in degrees per second."""
    rows = [row for row in beat["frames"]["rows"] if start <= row[0] <= end]
    picks = columns(beat)
    return max(abs(after[i] - before[i]) / (after[0] - before[0]) for before, after in pairwise(rows) for i in picks)


def find(beat: dict[str, Any], **wanted: Any) -> dict[str, Any]:
    for message in beat["messages"]:
        if all(message.get(key) == value for key, value in wanted.items()):
            return dict(message)
    raise AssertionError(f"no message with {wanted} in {beat['name']}")


def audits(beat: dict[str, Any], event: str) -> list[dict[str, Any]]:
    return [
        message["event"]
        for message in beat["messages"]
        if message["via"] == "live" and message["event"].get("type") == "audit" and message["event"]["event"] == event
    ]


def check_rate(beat: dict[str, Any], rate: int) -> str:
    times = [row[0] for row in beat["frames"]["rows"]]
    gaps = [after - before for before, after in pairwise(times)]
    worst = max(abs(gap - 1 / rate) for gap in gaps)
    assert worst < 2e-4, f"{beat['name']} frames drift {worst * 1000:.2f} ms from {rate} Hz"
    return f"{len(times)} frames at {rate} Hz"


def check_devices(beat: dict[str, Any]) -> str:
    connected = sorted(event["device"] for event in audits(beat, "connect") if event["status"] == "done")
    assert connected == ["bench-psu", "plant-waterer", "printer"], f"connect events for {connected}"
    return f"connect events for {', '.join(connected)}"


def check_limit(beat: dict[str, Any]) -> str:
    sent = find(beat, source="agent", tool="action", kind="request")
    answer = find(beat, source="hub", tool="action", kind="response")
    error = answer["result"]["error"]
    assert (error["code"], error["name"]) == (-32010, "LIMIT_EXCEEDED"), error
    most = moved(beat, sent["t"], beat["t_end"])
    assert most <= STILL_DEG, f"a joint moved {most:.4f} deg while the hub blocked the move"
    return f"LIMIT_EXCEEDED, joints moved at most {most:.4f} deg in {beat['t_end'] - sent['t']:.1f} s"


def check_approval(beat: dict[str, Any]) -> str:
    answers = [message for message in beat["messages"] if message.get("tool") == "action"]
    held = next((message for message in answers if (message.get("result") or {}).get("status") == "pending"), None)
    assert held is not None, "no action came back pending"
    request = held["result"]["request_id"]
    approved = find(beat, source="hub", path=f"/v1/confirmations/{request}/approve", kind="response")
    assert approved["result"]["status"] == "done", approved["result"]
    assert approved["t"] > held["t"]
    return f"pending at {held['t']:.2f} s, approved and done at {approved['t']:.2f} s"


def check_stop(beat: dict[str, Any]) -> str:
    pressed = find(beat, source="person", path="/v1/stop", kind="request")
    answered = find(beat, source="hub", path="/v1/stop", kind="response")
    arm = next(item for item in answered["result"]["devices"] if item["device"] == "arm")
    assert arm["status"] == "safe", arm
    before = speed(beat, pressed["t"] - 0.2, pressed["t"])
    assert before >= MOVING_DEG_S, f"the arm turned at most {before:.1f} deg/s before STOP"
    settle = moved(beat, pressed["t"], answered["t"])
    most = moved(beat, answered["t"], beat["t_end"])
    assert most <= STILL_DEG, f"a joint moved {most:.4f} deg after STOP"
    return (
        f"turning at {before:.0f} deg/s when STOP was pressed, {settle:.2f} deg more until the hub's reply "
        f"{(answered['t'] - pressed['t']) * 1000:.0f} ms later, then at most {most:.4f} deg "
        f"in {beat['t_end'] - answered['t']:.1f} s"
    )


CHECKS = {"devices": check_devices, "limit": check_limit, "approval": check_approval, "stop": check_stop}


def main() -> int:
    session = load("session.json")
    rate = session["frames"]["rate_hz"]
    failed = 0
    size = (HERE / "session.json").stat().st_size
    for entry in session["beats"]:
        beat = load(entry["file"])
        size += (HERE / entry["file"]).stat().st_size
        for name, check in (("rate", lambda b: check_rate(b, rate)), ("beat", CHECKS.get(beat["name"]))):
            if check is None:
                continue
            try:
                print(f"ok    {beat['name']} {name}: {check(beat)}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL  {beat['name']} {name}: {exc}")
    if size > MAX_BYTES:
        failed += 1
        print(f"FAIL  the data is {size / 1e6:.1f} MB, over {MAX_BYTES / 1e6:.0f} MB")
    else:
        print(f"ok    size: {size / 1e6:.2f} MB in total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
