"""Cut the film in Remotion from the rendered shots, lay the sound under it and write the cuts.

    uv run python video/scenes/assemble.py --scale 0.25
    uv run python video/scenes/assemble.py --scale 0.25 --stills
    uv run python video/scenes/assemble.py --scale 0.6666666667 --crf 14 --out video/out/final

The script copies the fonts and the wordmark into video/out/public, the folder Remotion serves,
next to the shot videos render_film.py wrote there. The edit is laid out at 3840 by 2160 and
--scale sets the output size, so 0.25 gives 960 by 540 and two thirds gives 2560 by 1440.
Remotion renders the Film and FilmVertical compositions without sound, from PNG frames, tagged
BT.709. sound.py writes the effects and the music bed, ffmpeg measures the mix and sets it to
-14 LUFS integrated with true peaks at most -1 dBTP in two loudnorm passes, and the mix is muxed
under each cut. Outputs go to --out, video/out/preview/ by default. --stills renders the
storyboard instead, one still per beat at the same scale, from the 3D stills render_film.py
--stills wrote at that size, then the YouTube thumbnail and the poster.
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


BUNDLE = OUT / "bundle"


def bundle() -> None:
    """Bundle the Remotion project once with the film's public folder, for every render after it."""
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    run(["pnpm", "exec", "remotion", "bundle", f"--out-dir={BUNDLE}", f"--public-dir={PUBLIC}"], cwd=REMOTION)


def remotion(command: str, args: list[str]) -> None:
    """Run a Remotion CLI command against the bundle."""
    run(["pnpm", "exec", "remotion", command, str(BUNDLE), *args], cwd=REMOTION)


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
    trim = TARGET_LUFS - float(result.get("output_i", TARGET_LUFS))
    if abs(trim) > 0.1 and float(result.get("output_tp", 0.0)) + trim <= TRUE_PEAK:
        trimmed = target.with_suffix(".trim.wav")
        run(
            [
                str(FFMPEG),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(target),
                "-af",
                f"volume={trim:.2f}dB",
                "-c:a",
                "pcm_s24le",
                str(trimmed),
            ]
        )
        trimmed.replace(target)
        result["output_i"] = str(float(result["output_i"]) + trim)
        result["output_tp"] = str(float(result["output_tp"]) + trim)
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
    p.add_argument("--music", default="", help="an outside 48 kHz PCM WAV in place of the generated bed")
    p.add_argument("--out", default=str(PREVIEW))
    p.add_argument("--crf", type=int, default=18)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--thumbnail-beat", type=int, default=6)
    p.add_argument("--poster-beat", type=int, default=2)
    opts = p.parse_args()
    public()
    target = Path(opts.out).resolve()
    target.mkdir(parents=True, exist_ok=True)
    edit = json.loads((SCENES / "shots" / "film" / "edit.json").read_text())
    if opts.stills:
        plan = json.loads((SCENES / "film.json").read_text())
        w, h = edit["resolution"]["landscape"]
        size = f"{round(w * opts.scale)}x{round(h * opts.scale)}"
        (PUBLIC / "stills").mkdir(parents=True, exist_ok=True)
        for still in plan["stills"]:
            source = OUT / "stills" / f"{still['shot']}-{size}.png"
            shutil.copy2(source, PUBLIC / "stills" / f"{still['shot']}-landscape.png")
        bundle()
        beats = [s["storyboard"] for s in plan["stills"]] + [8]
        renders = [
            ("Storyboard", f"storyboard-{beat}-{size}.png", {"aspect": "landscape", "beat": beat}) for beat in beats
        ]
        renders += [
            ("Thumbnail", f"thumbnail-{size}.png", {"beat": opts.thumbnail_beat}),
            ("Storyboard", f"poster-{size}.png", {"aspect": "landscape", "beat": opts.poster_beat}),
        ]
        for composition, name, props in renders:
            remotion(
                "still",
                [
                    composition,
                    str(target / name),
                    f"--props={json.dumps(props)}",
                    f"--scale={opts.scale}",
                    "--timeout=300000",
                ],
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
    bundle()
    for aspect in opts.aspects.split(","):
        w, h = edit["resolution"][aspect]
        size = f"{round(w * opts.scale)}x{round(h * opts.scale)}"
        silent = OUT / "edit" / f"film-{aspect}-{size}-silent.mp4"
        silent.parent.mkdir(parents=True, exist_ok=True)
        remotion(
            "render",
            [
                COMPOSITIONS[aspect],
                str(silent),
                f"--scale={opts.scale}",
                "--muted",
                f"--crf={opts.crf}",
                "--image-format=png",
                "--color-space=bt709",
                f"--concurrency={opts.concurrency}",
                "--timeout=300000",
            ],
        )
        final = target / f"openhal-film-{aspect}-{size}.mp4"
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
