"""Render the demo video in chunks of whole scenes, then join the chunks and add the sound.

    .venv/bin/python video/scenes/render_demo.py --scale 2 --out video/out/openhal-demo-1440p.mp4

Each chunk renders from the bundle in video/out/demo/bundle/ under nice, at a low concurrency, with
pmset's CPU speed limit read before and after. When the limit falls below 60 percent of its value
at the start of the run, the next chunk waits and renders on one tab. The chunks join with ffmpeg's
concat demuxer without re-encoding, and the sound from video/assets/demo/mix.wav goes in as AAC at
48 kHz. Each chunk is deleted once the video is joined.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

VIDEO = Path(__file__).resolve().parent.parent
REMOTION = VIDEO / "remotion"
BUNDLE = VIDEO / "out" / "demo" / "bundle"
EDIT = REMOTION / "src" / "demo" / "edit.json"
SOUND = VIDEO / "assets" / "demo" / "mix.wav"
FFMPEG = Path.home() / ".local/opt/ffmpeg-9.0.2/bin/ffmpeg"
CHUNK_FRAMES = 420


def speed_limit() -> int:
    """pmset's CPU speed limit in percent."""
    text = subprocess.run(["/usr/bin/pmset", "-g", "therm"], capture_output=True, text=True, check=False).stdout
    match = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", text)
    return int(match.group(1)) if match else 100


def chunks(edit: dict) -> list[tuple[int, int, list[str]]]:
    """Whole scenes grouped into chunks of about CHUNK_FRAMES frames, as first frame, last frame and scene ids."""
    out: list[tuple[int, int, list[str]]] = []
    for scene in edit["scenes"]:
        first, last = scene["from"], scene["from"] + scene["frames"] - 1
        if out and last - out[-1][0] < CHUNK_FRAMES:
            out[-1] = (out[-1][0], last, [*out[-1][2], scene["id"]])
        else:
            out.append((first, last, [scene["id"]]))
    return out


def render(first: int, last: int, scale: float, concurrency: int, crf: int, target: Path) -> float:
    """Render one frame range without sound and return the wall time."""
    start = time.monotonic()
    command = [
        "/usr/bin/nice", "-n", "10", "/usr/local/bin/pnpm", "exec", "remotion", "render", str(BUNDLE), "OpenHALDemo",
        str(target), f"--frames={first}-{last}", f"--scale={scale}", f"--concurrency={concurrency}", "--gl=angle",
        f"--crf={crf}", "--muted", "--props", json.dumps({"sound": False}), "--timeout=300000", "--overwrite",
        "--log=error",
    ]  # fmt: skip
    subprocess.run(command, cwd=REMOTION, check=True)  # noqa: S603
    return time.monotonic() - start


def main() -> int:
    """Render, join and mux."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--pause", type=float, default=20.0)
    args = parser.parse_args()
    edit = json.loads(EDIT.read_text(encoding="utf-8"))
    args.out = args.out.resolve()
    work = args.out.parent / f".{args.out.stem}-chunks"
    work.mkdir(parents=True, exist_ok=True)
    baseline = speed_limit()
    concurrency = args.concurrency
    parts: list[Path] = []
    total = 0.0
    for index, (first, last, ids) in enumerate(chunks(edit)):
        before = speed_limit()
        if before < 0.6 * baseline:
            print(f"speed limit {before} percent, under 60 percent of {baseline}, waiting and dropping to one tab")
            time.sleep(args.pause * 3)
            concurrency = 1
        target = work / f"part-{index:02d}.mp4"
        seconds = render(first, last, args.scale, concurrency, args.crf, target)
        after = speed_limit()
        frames = last - first + 1
        total += seconds
        span = f"{' '.join(ids):34} frames {first:4} to {last:4}, {seconds:6.1f} s, {seconds / frames:.3f} s a frame"
        print(f"{span}, concurrency {concurrency}, speed limit {before} then {after} percent")
        parts.append(target)
        time.sleep(args.pause)
    listing = work / "parts.txt"
    listing.write_text("".join(f"file '{part.name}'\n" for part in parts), encoding="utf-8")
    silent = work / "silent.mp4"
    join = [
        str(FFMPEG),
        "-v",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        str(silent),
    ]
    subprocess.run(join, check=True)  # noqa: S603
    mux = [
        str(FFMPEG), "-v", "error", "-y", "-i", str(silent), "-i", str(SOUND), "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
        str(args.out),
    ]  # fmt: skip
    subprocess.run(mux, check=True)  # noqa: S603
    for part in [*parts, listing, silent]:
        part.unlink()
    work.rmdir()
    print(f"wrote {args.out}, {total:.1f} s of rendering for {edit['frames']} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
