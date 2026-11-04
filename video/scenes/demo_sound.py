"""Mix the demo video's sound from real recordings and one human-composed track.

    .venv/bin/python video/scenes/demo_sound.py --cues video/remotion/src/demo/cues.json \\
        --sources video/out/sound-sources --out video/out/demo/sound/mix-raw.wav --normalize video/assets/demo/mix.wav

The sources are the files named in SOURCES, downloaded into one folder. video/CREDITS.md gives each
file's author, page and license.

- Music. "Inspired" by Kevin MacLeod plays from the start and stops dead on the STOP click, then
  comes back from a later bar under the stat cards and fades out on the end card.
- Typing. Single key presses cut from a recording of a keyboard, one for each character of a
  prompt as the prompt types out.
- Clicks. A recorded mouse click on Approve and on STOP.
- Switch. A recorded switch under STOP, and quieter where the hub answers LIMIT_EXCEEDED.
- Servo. A recorded stepper motor, looped, with its playback rate and level following the arm's
  recorded joint speed on screen, so the motor speeds up, slows and stops with the arm.

The output is 48 kHz, 24-bit stereo PCM. --normalize measures the mix with ffmpeg's loudnorm in
two passes and writes a copy at -14 LUFS integrated with the true peak under -1.5 dBTP.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

RATE = 48_000
FFMPEG = Path.home() / ".local/opt/ffmpeg-9.0.2/bin/ffmpeg"
SEED = 5
SOURCES = {
    "music": "Inspired.mp3",
    "typing": "keychron-typing.wav",
    "click": "mouse-single-click.ogg",
    "switch": "clickick-switch.ogg",
    "servo": "nema17_10mm.wav",
}
SERVO_LOOP = (0.42, 1.02)
"""Seconds of the stepper recording looped for the servo, the steady middle of its first move."""
SPEED_LIMIT = 60.0
LEVELS = {"music": -8.0, "typing": -13.0, "click": -9.0, "switch": 0.0, "servo": -11.0}
"""Gains in dB before loudness normalization, the music under the effects."""


def db(value: float) -> float:
    """Amplitude for a level in dB."""
    return 10 ** (value / 20)


def load(path: Path) -> np.ndarray:
    """Decode a file to 48 kHz stereo float samples, shape (n, 2)."""
    raw = subprocess.run(  # noqa: S603
        [str(FFMPEG), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(np.float64)


def keystrokes(typing: np.ndarray, count: int = 40) -> list[np.ndarray]:
    """Single key presses cut at the onsets of a typing recording."""
    mono = np.abs(typing.mean(axis=1))
    window = int(0.004 * RATE)
    envelope = np.convolve(mono, np.ones(window) / window, mode="same")
    threshold = np.percentile(envelope, 97)
    gap = int(0.09 * RATE)
    onsets: list[int] = []
    i = 0
    while i < len(envelope) and len(onsets) < count:
        if envelope[i] > threshold and (not onsets or i - onsets[-1] > gap):
            onsets.append(max(0, i - int(0.004 * RATE)))
            i += gap
        else:
            i += 1
    length = int(0.085 * RATE)
    fade = np.linspace(1, 0, int(0.02 * RATE))
    clips = []
    for start in onsets:
        clip = typing[start : start + length].copy()
        clip[-len(fade) :] *= fade[:, None]
        clips.append(clip / (np.max(np.abs(clip)) or 1))
    return clips


def servo_voice(loop: np.ndarray, speeds: list[float], fps: float) -> np.ndarray:
    """The motor loop played at a rate and level that follow per-frame joint speeds in deg/s."""
    n = int(len(speeds) / fps * RATE)
    if n <= 0:
        return np.zeros((0, 2))
    t = np.arange(n) / RATE
    control = np.clip(np.interp(t, np.arange(len(speeds)) / fps, np.asarray(speeds, dtype=float)) / SPEED_LIMIT, 0, 1.2)
    smooth = int(0.03 * RATE)
    control = np.convolve(control, np.ones(smooth) / smooth, mode="same")
    rate = 0.75 + 0.5 * control
    phase = np.cumsum(rate) % len(loop)
    base = np.floor(phase).astype(int)
    frac = phase - base
    nxt = (base + 1) % len(loop)
    out = loop[base] * (1 - frac)[:, None] + loop[nxt] * frac[:, None]
    return out * (np.clip(control, 0, 1) ** 0.7)[:, None]


def add(mix: np.ndarray, at: float, sound: np.ndarray, gain: float) -> None:
    """Add a stereo sound into the mix at a time in seconds."""
    start = int(at * RATE)
    if start >= len(mix):
        return
    end = min(len(mix), start + len(sound))
    mix[start:end] += sound[: end - start] * gain


def build(cues: dict, folder: Path) -> np.ndarray:
    """Render every cue into a stereo mix."""
    rng = np.random.default_rng(SEED)
    fps = float(cues["fps"])
    sound = {name: load(folder / file) for name, file in SOURCES.items()}
    mix = np.zeros((int(cues["duration"] * RATE) + RATE, 2))
    music = sound["music"] / (np.max(np.abs(sound["music"])) or 1)
    for part in cues["music"]:
        length = int((part["end"] - part["start"]) * RATE)
        piece = music[int(part["offset"] * RATE) : int(part["offset"] * RATE) + length].copy()
        fade_in = int(part.get("fade_in", 0.05) * RATE)
        piece[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
        tail = int(part.get("fade_out", 0.006) * RATE)
        piece[-tail:] *= np.linspace(1, 0, tail)[:, None]
        add(mix, part["start"], piece, db(LEVELS["music"]))
    keys = keystrokes(sound["typing"])
    for typing in cues["typing"]:
        span = typing["end"] - typing["start"]
        for i in range(typing["chars"]):
            if rng.random() < 0.12:
                continue
            clip = keys[int(rng.integers(len(keys)))]
            add(
                mix,
                typing["start"] + span * i / typing["chars"] + 0.006 * rng.standard_normal(),
                clip,
                db(LEVELS["typing"] + rng.uniform(-2, 1)),
            )
    click = sound["click"] / (np.max(np.abs(sound["click"])) or 1)
    for at in cues["clicks"]:
        add(mix, at, click, db(LEVELS["click"]))
    switch = sound["switch"] / (np.max(np.abs(sound["switch"])) or 1)
    for cue in cues["switches"]:
        add(mix, cue["at"], switch, db(LEVELS["switch"] + cue.get("level", 0)))
    a, b = (int(v * RATE) for v in SERVO_LOOP)
    loop = sound["servo"][a:b]
    loop = loop / (np.max(np.abs(loop)) or 1)
    for servo in cues["servos"]:
        add(mix, servo["start"], servo_voice(loop, servo["speeds"], fps), db(LEVELS["servo"]))
    return mix[: int(cues["duration"] * RATE)]


def write_wav(path: Path, mix: np.ndarray) -> None:
    """Write 24-bit stereo PCM, scaled so the peak sits at -3 dBFS before loudness is set."""
    peak = np.max(np.abs(mix)) or 1e-9
    data = mix * (db(-3) / peak)
    ints = np.clip(np.round(data * (2**23 - 1)), -(2**23), 2**23 - 1).astype(np.int32)
    raw = ints.reshape(-1).astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(RATE)
        handle.writeframes(raw)


def normalize(source: Path, target: Path) -> dict:
    """Two pass loudnorm to -14 LUFS integrated and -1.5 dBTP, written as 24-bit PCM at 48 kHz."""
    first = subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    stats = json.loads(first[first.rindex("{") : first.rindex("}") + 1])
    filt = (
        "loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:"
        f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}:"
        f"measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(FFMPEG),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-i",
        str(source),
        "-af",
        filt,
        "-ar",
        str(RATE),
        "-c:a",
        "pcm_s24le",
        str(target),
    ]
    subprocess.run(command, check=True)  # noqa: S603
    return stats


def main() -> int:
    """Read the cue sheet and write the mix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cues", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--normalize", type=Path)
    args = parser.parse_args()
    cues = json.loads(args.cues.read_text(encoding="utf-8"))
    mix = build(cues, args.sources)
    write_wav(args.out, mix)
    print(f"wrote {args.out}, {len(mix) / RATE:.2f} s")
    if args.normalize:
        stats = normalize(args.out, args.normalize)
        print(f"normalized to {args.normalize} from {stats['input_i']} LUFS and {stats['input_tp']} dBTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
