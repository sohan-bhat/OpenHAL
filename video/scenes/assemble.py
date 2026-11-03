"""Cut the film in Remotion from the rendered shots, lay the sound under it and write the previews.

    uv run python video/scenes/assemble.py --scale 0.25
    uv run python video/scenes/assemble.py --scale 0.25 --stills

The script copies the fonts and the wordmark into video/out/public, the folder Remotion serves,
next to the shot videos render_film.py wrote there. Remotion renders the Film and FilmVertical
compositions without sound. sound.py writes the effects mix, ffmpeg measures it and sets it to
-14 LUFS integrated with true peaks at most -1 dBTP in two loudnorm passes, and the mix is muxed
under each cut. Every output goes to video/out/preview/. --stills renders the storyboard instead,
one still per beat, from the 3D stills render_film.py --stills wrote.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCENES = Path(__file__).resolve().parent
VIDEO = SCENES.parent
REPO = VIDEO.parent
OUT = VIDEO / "out"
PUBLIC = OUT / "public"
PREVIEW = OUT / "preview"
REMOTION = VIDEO / "remotion"
FFMPEG = Path.home() / ".local" / "opt" / "ffmpeg-9.0.2" / "bin" / "ffmpeg"
TARGET_LUFS = -14.0
TRUE_PEAK = -1.0
COMPOSITIONS = {"landscape": "Film", "vertical": "FilmVertical"}


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command and fail loudly."""
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)  # noqa: S603


def public() -> None:
    """Fonts and the dark wordmark next to the rendered shots."""
    (PUBLIC / "fonts").mkdir(parents=True, exist_ok=True)
    (PUBLIC / "brand").mkdir(parents=True, exist_ok=True)
    for font in (REPO / "design" / "fonts").glob("*.woff2"):
        shutil.copy2(font, PUBLIC / "fonts" / font.name)
    shutil.copy2(REPO / "docs" / "assets" / "wordmark-dark.svg", PUBLIC / "brand" / "wordmark-dark.svg")


def remotion(args: list[str]) -> None:
    """Run the Remotion CLI from the project folder against the film's public folder."""
    run(["pnpm", "exec", "remotion", *args, f"--public-dir={PUBLIC}"], cwd=REMOTION)


def loudness(source: Path, target: Path) -> dict[str, float]:
    """Two loudnorm passes to TARGET_LUFS and TRUE_PEAK, then a check of the result."""
    first = run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-af",
            f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=20:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", first.stderr)
    if found is None:
        raise SystemExit("loudnorm printed no measurement")
    m = json.loads(found.group(0))
    chain = (
        f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=20:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
        f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
        "linear=true:print_format=json"
    )
    second = run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(source),
            "-af",
            chain,
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            str(target),
        ]
    )
    found = re.search(r"\{[^{}]*\"output_i\"[^{}]*\}", second.stderr)
    result = json.loads(found.group(0)) if found else {}
    return {
        "input_i": float(m["input_i"]),
        "input_tp": float(m["input_tp"]),
        "output_i": float(result.get("output_i", "nan")),
        "output_tp": float(result.get("output_tp", "nan")),
        "type": result.get("normalization_type", "unknown"),
    }


def measure(path: Path) -> str:
    """Integrated loudness and true peak of a file's audio, from ebur128."""
    out = run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true:framelog=quiet",
            "-f",
            "null",
            "-",
        ]
    )
    lines = [line.strip() for line in out.stderr.splitlines() if re.match(r"\s+(I|Peak|LRA):", line)]
    return ", ".join(lines)


def main() -> int:
    """Edit, sound and mux both cuts, or render the storyboard stills."""
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=float, default=0.25)
    p.add_argument("--aspects", default="landscape,vertical")
    p.add_argument("--stills", action="store_true")
    p.add_argument("--music", default="")
    opts = p.parse_args()
    public()
    PREVIEW.mkdir(parents=True, exist_ok=True)
    edit = json.loads((SCENES / "shots" / "film" / "edit.json").read_text())
    if opts.stills:
        plan = json.loads((SCENES / "film.json").read_text())
        (PUBLIC / "stills").mkdir(parents=True, exist_ok=True)
        for still in plan["stills"]:
            for aspect in ("landscape",):
                source = OUT / "stills" / f"{still['shot']}-1920x1080.png"
                shutil.copy2(source, PUBLIC / "stills" / f"{still['shot']}-{aspect}.png")
        beats = [s["storyboard"] for s in plan["stills"]] + [8]
        for beat in beats:
            props = json.dumps({"aspect": "landscape", "beat": beat})
            remotion(
                [
                    "still",
                    "Storyboard",
                    str(PREVIEW / f"storyboard-{beat}-1920x1080.png"),
                    f"--props={props}",
                    "--scale=0.5",
                    "--timeout=300000",
                ]
            )
        return 0
    sound_raw = OUT / "sound" / "fx.wav"
    sound_cmd = [sys.executable, str(SCENES / "sound.py"), "--out", str(sound_raw)]
    if opts.music:
        sound_cmd += ["--music", opts.music]
    run(sound_cmd)
    mixed = OUT / "sound" / "film-14lufs.wav"
    stats = loudness(sound_raw, mixed)
    print(f"loudness {stats}", flush=True)
    for aspect in opts.aspects.split(","):
        w, h = edit["resolution"][aspect]
        size = f"{round(w * opts.scale)}x{round(h * opts.scale)}"
        silent = OUT / "edit" / f"film-{aspect}-{size}-silent.mp4"
        silent.parent.mkdir(parents=True, exist_ok=True)
        remotion(
            [
                "render",
                COMPOSITIONS[aspect],
                str(silent),
                f"--scale={opts.scale}",
                "--muted",
                "--crf=18",
                "--timeout=300000",
            ]
        )
        final = PREVIEW / f"openhal-film-{aspect}-{size}.mp4"
        run(
            [
                str(FFMPEG),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(silent),
                "-i",
                str(mixed),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(final),
            ]
        )
        print(f"{final}: {measure(final)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
