"""Render the film's 3D shots one at a time, encode each one and delete its frames.

    python3 -I video/scenes/render_film.py --aspect landscape --width 960 --height 540 --samples 8

Each shot runs film_shot.py in a headless Blender, writes PNG frames to video/out/frames/,
encodes them with ffmpeg to video/out/public/shots/<shot>-<aspect>.mp4 and deletes the frames
before the next shot starts. Before a shot starts, the script checks the free disk space against
the shot's frames at the measured size per frame, and stops when the free space would fall under
the floor. Every shot's wall time and every frame's render time go to video/out/times/.

--stills renders one storyboard still per shot listed in film.json's stills, as PNG files in
video/out/stills/, with no encode. --measure renders only the frames --frames names in each shot,
records their render time and PNG size and deletes them, for planning a full render.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCENES = Path(__file__).resolve().parent
VIDEO = SCENES.parent
OUT = VIDEO / "out"
BLENDER = Path.home() / "Applications" / "Blender-4.5.15.app" / "Contents" / "MacOS" / "Blender"
FFMPEG = Path.home() / ".local" / "opt" / "ffmpeg-9.0.2" / "bin" / "ffmpeg"
FLOOR_GB = 2.5
"""Free space the run never goes under."""


def free_gb(path: Path = VIDEO) -> float:
    """Free space on the volume that holds path, in GB."""
    return shutil.disk_usage(path).free / 1e9


def blender(
    shot: str, aspect: str, width: int, height: int, samples: int, engine: str, out: Path, frames: str, log: Path
) -> None:
    """Run film_shot.py for one shot and wait for it."""
    cmd = [
        str(BLENDER),
        "-b",
        "--factory-startup",
        "-noaudio",
        "--python",
        str(SCENES / "film_shot.py"),
        "--",
        "--shot",
        shot,
        "--aspect",
        aspect,
        "--engine",
        engine,
        "--width",
        str(width),
        "--height",
        str(height),
        "--samples",
        str(samples),
        "--out",
        str(out),
    ]
    if frames:
        cmd += ["--frames", frames]
    with log.open("w") as handle:
        proc = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT)  # noqa: S603
        print(f"  blender pid {proc.pid}", flush=True)
        code = proc.wait()
    if code != 0:
        raise SystemExit(f"Blender failed on {shot} {aspect}, see {log}")


def encode(frames_dir: Path, target: Path, fps: int, crf: int) -> None:
    """Encode a PNG sequence to H.264."""
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(FFMPEG),
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(target),
    ]
    subprocess.run(cmd, check=True)  # noqa: S603


def main() -> int:
    """Render, encode and clean up each shot in turn."""
    p = argparse.ArgumentParser()
    p.add_argument("--aspect", choices=("landscape", "vertical"), default="landscape")
    p.add_argument("--width", type=int, default=960, help="landscape width, swapped with height for vertical")
    p.add_argument("--height", type=int, default=540)
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    p.add_argument("--shots", default="", help="comma-separated shot ids, all shots when empty")
    p.add_argument("--crf", type=int, default=16)
    p.add_argument("--stills", action="store_true")
    p.add_argument("--measure", action="store_true")
    p.add_argument("--frames", default="", help="frames to render in each shot, with --measure")
    p.add_argument("--mb-per-frame", type=float, default=0.0, help="disk per PNG frame, measured when 0")
    opts = p.parse_args()
    plan = json.loads((SCENES / "film.json").read_text())
    width, height = (opts.width, opts.height) if opts.aspect == "landscape" else (opts.height, opts.width)
    wanted = [s for s in opts.shots.split(",") if s]
    shots = [s for s in plan["shots"] if not wanted or s["id"] in wanted]
    stills = {s["shot"]: s["frame"] for s in plan.get("stills", [])}
    if opts.stills:
        shots = [s for s in shots if s["id"] in stills]
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    (OUT / "times").mkdir(parents=True, exist_ok=True)
    label = f"{opts.aspect}-{width}x{height}-{opts.engine}-{opts.samples}"
    kind = "stills" if opts.stills else "measure" if opts.measure else "shots"
    summary_path = OUT / "times" / f"{kind}-{label}.csv"
    new = not summary_path.exists()
    mb = opts.mb_per_frame or (width * height * 3 / 1e6) * 0.55
    with summary_path.open("a", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(
                [
                    "shot",
                    "aspect",
                    "width",
                    "height",
                    "engine",
                    "samples",
                    "frames",
                    "wall_s",
                    "mb_per_frame",
                    "free_gb_after",
                ]
            )
        for spec in shots:
            shot_file = json.loads((SCENES / "shots" / "film" / f"{spec['id']}.json").read_text())
            count = 1 if opts.stills else len(opts.frames.split(",")) if opts.measure else shot_file["frames"]
            need = count * mb / 1e3
            free = free_gb()
            if free - need < FLOOR_GB:
                print(
                    f"stop: {free:.2f} GB free, {spec['id']} needs about {need:.2f} GB, floor {FLOOR_GB} GB", flush=True
                )
                return 2
            name = f"{spec['id']}-{opts.aspect}"
            frames_dir = OUT / ("frames" if kind == "shots" else f"{kind}-frames") / name
            if frames_dir.exists():
                shutil.rmtree(frames_dir)
            print(f"{name}: {count} frames at {width}x{height}, {free:.2f} GB free", flush=True)
            start = time.perf_counter()
            frames = str(stills[spec["id"]]) if opts.stills else opts.frames if opts.measure else ""
            blender(
                spec["id"],
                opts.aspect,
                width,
                height,
                opts.samples,
                opts.engine,
                frames_dir,
                frames,
                OUT / "logs" / f"{name}-{label}.log",
            )
            pngs = sorted(frames_dir.glob("frame_*.png"))
            used = sum(f.stat().st_size for f in pngs) / 1e6
            mb = used / max(len(pngs), 1)
            per_frame = OUT / "times" / f"{name}-{label}-frames.csv"
            shutil.copyfile(frames_dir / "times.csv", per_frame)
            if opts.measure:
                pass
            elif opts.stills:
                target = OUT / "stills" / f"{spec['id']}-{width}x{height}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pngs[0], target)
            else:
                encode(frames_dir, OUT / "public" / "shots" / f"{name}.mp4", shot_file["fps"], opts.crf)
            shutil.rmtree(frames_dir)
            wall = time.perf_counter() - start
            writer.writerow(
                [
                    spec["id"],
                    opts.aspect,
                    width,
                    height,
                    opts.engine,
                    opts.samples,
                    count,
                    f"{wall:.1f}",
                    f"{mb:.3f}",
                    f"{free_gb():.2f}",
                ]
            )
            handle.flush()
            print(f"  done in {wall:.0f} s, {mb:.2f} MB a frame, {free_gb():.2f} GB free", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
