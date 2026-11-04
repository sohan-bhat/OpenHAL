"""Synthesize the demo video's sound from its cue sheet, with no recorded audio.

    uv run python video/scenes/demo_sound.py --cues video/remotion/src/demo/cues.json --out video/out/demo/sound/mix.wav

The cue sheet comes from demo_edit.py, from the same edit and take the pictures use.

- Music. A bed at 112 BPM in the series' manner, a kick, a soft hat, a bass on the chord's root, a
  pluck stepping through the chord and a pad. Each section of the edit sets how many of those parts
  play, and the chord changes on the section's first beat.
- Typing. A soft key click for each character as the prompt types out.
- Tool calls. A click when a call appears and a lighter tick when its result lands.
- Servo whir. A voice whose pitch and level follow the arm's recorded joint speed on screen.
- The block. A low tone on LIMIT_EXCEEDED, and the bed drops to the pad under the block.
- Approval. A tap on the click and a two note chime when the hub runs the held command.
- STOP. A firm click, then silence for the cue's span.

The output is 48 kHz, 24-bit stereo PCM. --normalize measures the mix with ffmpeg's loudnorm in two
passes and writes a copy at -14 LUFS integrated with the true peak under -1.5 dBTP.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sound as s

RATE = s.RATE
BPM = 112.0
BEAT = 60.0 / BPM
SEED = 11
FFMPEG = Path.home() / ".local/opt/ffmpeg-9.0.2/bin/ffmpeg"
CHORDS = {
    "a": (("A1", "E2", "A2"), ("A3", "C4", "E4", "B3")),
    "f": (("F1", "C2", "F2"), ("F3", "A3", "C4", "E4")),
    "c": (("C2", "G2", "C3"), ("G3", "C4", "E4", "D4")),
    "g": (("G1", "D2", "G2"), ("G3", "B3", "D4", "A3")),
    "d": (("D2", "A2", "D3"), ("F3", "A3", "D4", "E4")),
}
PARTS = {
    0: (),
    1: ("pad",),
    2: ("pad", "pluck"),
    3: ("pad", "pluck", "bass", "hat"),
    4: ("pad", "pluck", "bass", "hat", "kick"),
}


def kick() -> np.ndarray:
    """A short sine kick that drops from 120 to 48 Hz."""
    n = int(0.42 * RATE)
    t = np.arange(n) / RATE
    f = 48 + 72 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * s.envelope(n, 0.001, 0.16)


def hat(rng: np.random.Generator) -> np.ndarray:
    """A soft closed hat."""
    n = int(0.06 * RATE)
    return s.band_noise(n, 6000, 14000, rng) * s.envelope(n, 0.0005, 0.018)


def bass(freq: float, length: float) -> np.ndarray:
    """A round bass note, a sine with a little second harmonic."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    phase = 2 * np.pi * freq * t
    return (np.sin(phase) + 0.25 * np.sin(2 * phase)) * s.envelope(n, 0.006, length * 0.55)


def key_click(rng: np.random.Generator) -> np.ndarray:
    """One soft key press."""
    return s.click(rng, 1800 + 500 * rng.random(), 0.035)


def whir(speeds: list[float], fps: float, limit: float) -> np.ndarray:
    """A servo voice for a list of per-frame joint speeds in deg/s."""
    n = int(len(speeds) / fps * RATE)
    if n <= 0:
        return np.zeros(0)
    t = np.arange(n) / RATE
    control = np.interp(t, np.arange(len(speeds)) / fps, np.asarray(speeds, dtype=float))
    level = np.clip(control / limit, 0, 1.4) ** 0.8
    freq = 150 + 260 * np.clip(control / limit, 0, 1.4)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    tone = np.sin(phase) + 0.35 * np.sin(2 * phase + 0.4) + 0.18 * np.sin(3 * phase + 1.1)
    buzz = np.sign(np.sin(phase * 0.5)) * 0.05
    return (tone + buzz) * level


def section_bed(
    mix: s.Mix, start: float, end: float, energy: int, chord: str, rng: np.random.Generator, first: bool
) -> None:
    """Fill one section with the parts its energy plays, on a grid that starts at the section."""
    roots, notes = CHORDS[chord]
    parts = PARTS[energy]
    length = end - start
    if "pad" in parts:
        mix.add(
            start,
            s.pad(
                [s.note(n) for n in roots] + [s.note(notes[0]), s.note(notes[2])], length, 0.25 if first else 0.06, 0.35
            ),
            s.db(-21),
        )
    steps = int(length / (BEAT / 2) + 1e-6)
    for i in range(steps):
        at = start + i * BEAT / 2
        if at >= end - 0.02:
            break
        on_beat = i % 2 == 0
        if "kick" in parts and on_beat:
            mix.add(at, kick(), s.db(-11))
        if "hat" in parts and not on_beat:
            mix.add(at, hat(rng), s.db(-30), pan=0.25)
        if "bass" in parts and on_beat:
            mix.add(at, bass(s.note(roots[0]) * (2 if (i // 2) % 4 == 3 else 1), BEAT * 0.9), s.db(-17))
        if "pluck" in parts:
            mix.add(at, s.pluck(s.note(notes[i % len(notes)]), 0.5), s.db(-27), pan=-0.3 + 0.6 * ((i % 4) / 3))


def build(cues: dict) -> tuple[np.ndarray, np.ndarray]:
    """Render every cue into a stereo mix."""
    rng = np.random.default_rng(SEED)
    fps = float(cues["fps"])
    mix = s.Mix(cues["duration"])
    for k, section in enumerate(cues["sections"]):
        section_bed(mix, section["start"], section["end"], section["energy"], section["chord"], rng, k == 0)
    for typing in cues.get("typing", []):
        count = max(1, typing["chars"])
        span = typing["end"] - typing["start"]
        for i in range(count):
            mix.add(
                typing["start"] + span * i / count + 0.004 * rng.standard_normal(),
                key_click(rng),
                s.db(-24),
                pan=0.1 * rng.standard_normal(),
            )
    for at in cues.get("calls", []):
        mix.add(at, s.click(rng, 1200, 0.06), s.db(-16))
    for at in cues.get("results", []):
        mix.add(at, s.click(rng, 2400, 0.04), s.db(-22))
    for at in cues.get("presses", []):
        mix.add(at, s.click(rng, 900, 0.08), s.db(-12))
    for at in cues.get("blocks", []):
        mix.add(at, s.low_tone(1.1), s.db(-9))
    for at in cues.get("chimes", []):
        mix.add(at, s.bell([s.note("E5"), s.note("B5")], 1.6, 0.5), s.db(-15), pan=-0.15)
        mix.add(at + 0.14, s.bell([s.note("A5"), s.note("E6")], 1.6, 0.55), s.db(-17), pan=0.15)
    for servo in cues.get("servos", []):
        voice = whir(servo["speeds"], fps, servo["limit"])
        mix.add(servo["start"], voice, s.db(-27))
    wet_l, wet_r = s.reverb(0.5 * (mix.left + mix.right), rng)
    left = mix.left + 0.16 * wet_l
    right = mix.right + 0.16 * wet_r
    for quiet in cues.get("silence", []):
        a, b = int(quiet["start"] * RATE), int(quiet["end"] * RATE)
        fade = int(0.004 * RATE)
        ramp = np.linspace(1, 0, fade)
        for channel in (left, right):
            channel[a : a + fade] *= ramp
            channel[a + fade : b] = 0
    end = int(cues["duration"] * RATE)
    fade_out = int(cues.get("fade_out", 1.2) * RATE)
    for channel in (left, right):
        channel[end - fade_out : end] *= np.linspace(1, 0, fade_out)
    return left[:end], right[:end]


def write_wav(path: Path, left: np.ndarray, right: np.ndarray) -> None:
    """Write 24-bit stereo PCM, scaled so the peak sits at -3 dBFS before loudness is set."""
    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-9)
    scale = s.db(-3) / peak
    data = np.stack([left * scale, right * scale], axis=1)
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
    subprocess.run(  # noqa: S603
        [
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
        ],
        check=True,
    )
    return stats


def main() -> int:
    """Read the cue sheet and write the mix."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cues", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--normalize", type=Path)
    args = parser.parse_args()
    cues = json.loads(args.cues.read_text(encoding="utf-8"))
    left, right = build(cues)
    write_wav(args.out, left, right)
    print(f"wrote {args.out}, {len(left) / RATE:.2f} s")
    if args.normalize:
        stats = normalize(args.out, args.normalize)
        print(f"normalized to {args.normalize} from {stats['input_i']} LUFS and {stats['input_tp']} dBTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
