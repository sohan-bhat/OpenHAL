"""Design the film's sound from its edit and the hub recording, with no recorded audio.

    uv run python video/scenes/sound.py --out video/out/sound/fx.wav [--music track.wav]

Every cue comes from the same edit.json and shot files the pictures use.

- Servo whir. Each joint is a voice whose pitch and level follow that joint's speed on screen,
  read from the recording, so the whir starts, swells and stops with the arm.
- Requests. A soft click when the agent sends a command and a higher tick when it reaches the layer.
- The block. A low tone when the hub blocks the move, on the hub's blocked event.
- The hold. A quiet two-note chime when the hub holds the drop, a tap and a brighter chime on approval.
- STOP. A firm click when the person presses STOP, then the room tone and the servos cut to silence
  on the freeze, through the black after the shot.
- Devices. A pluck for each device as the hub's connect event comes, one pitch per device.
- Room tone under everything else, a low swell under the cold open and a soft chord under the end card.
- The music bed, generated here like every other sound. Each beat of the edit holds one soft chord
  that changes on the beat's first cut, a clean pluck steps through the chord on a 100 BPM grid
  that restarts with each chord, and a low tock marks each cut inside a beat. The bed dips under the
  block, the hold, the approval and each device, and stops dead on the STOP press. It stays out
  through the black after STOP and comes back on the cut to the devices.

--music replaces the bed with an outside track in the music slot, 16 dB under the effects by
default and cut with everything else from STOP to the end of the black. That track's license goes
in video/CREDITS.md before it ships. --no-bed leaves the music out.
The script writes 48 kHz, 24-bit stereo PCM. Loudness is set afterwards by assemble.py.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import recording

SCENES = Path(__file__).resolve().parent
FILM = SCENES / "shots" / "film"
RATE = 48_000
CONTROL = 1_000
VOICES = {
    "shoulder_pan": (118.0, -0.2),
    "shoulder_lift": (96.0, 0.0),
    "elbow_flex": (134.0, 0.1),
    "wrist_flex": (186.0, 0.2),
    "wrist_roll": (232.0, 0.25),
    "gripper": (288.0, 0.3),
}
DEVICE_NOTES = {"printer": 523.25, "board": 659.25, "psu": 783.99}
SEED = 7
SEMITONES = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
BED = {
    1: (("A1", "E2", "A2"), ("A3", "E4")),
    2: (("A2", "E3", "B3"), ("A3", "E4", "B4", "E4")),
    3: (("F2", "C3", "E3", "A3"), ("F3", "C4", "E4", "G4", "A4", "G4", "E4", "C4")),
    4: (("D2", "A2", "E3"), ("D4", "A3", "E4", "A3")),
    5: (("E2", "B2", "D3", "G3"), ("E4", "G4", "B4", "D5", "B4", "G4")),
    6: (("A2", "E3", "B3"), ("A3", "E4", "B4", "D5")),
    7: (("A1", "E2", "G2", "C3"), ("A3", "C4", "E4", "G4")),
    8: (("A1", "E2", "C#3", "B3"), ("A3", "E4", "C#4", "B4")),
}
"""Each beat's chord and the notes its pluck steps through, by storyboard beat."""
STEP_S = 0.3
"""One grid step, an eighth note at 100 BPM."""
PLUCK_EVERY = {1: 2, 2: 1, 3: 1, 4: 2, 5: 1, 6: 1, 7: 2, 8: 2}
"""Grid steps between plucks in each beat."""
BED_TRIM_DB = {1: -3.0, 2: -3.0, 7: -3.0}
"""Beats where the bed sits lower, under the still arm and under the device plucks."""
BED_DB = -22.0
"""Level of the music bed against the effects, before loudness normalization."""


def db(value: float) -> float:
    """Amplitude for a level in dBFS."""
    return 10 ** (value / 20)


def envelope(n: int, attack: float, decay: float) -> np.ndarray:
    """An attack and exponential decay over n samples, times in seconds."""
    t = np.arange(n) / RATE
    rise = np.clip(t / max(attack, 1e-4), 0, 1)
    return rise * np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4))


def band_noise(n: int, low: float, high: float, rng: np.random.Generator) -> np.ndarray:
    """White noise kept between low and high Hz."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    spectrum[(freqs < low) | (freqs > high)] = 0
    out = np.fft.irfft(spectrum, n)
    return out / (np.max(np.abs(out)) or 1.0)


class Mix:
    """A stereo buffer with helpers to place sounds at film times."""

    def __init__(self, seconds: float) -> None:
        self.n = int(seconds * RATE) + RATE
        self.left = np.zeros(self.n)
        self.right = np.zeros(self.n)

    def add(self, at: float, mono: np.ndarray, gain: float, pan: float = 0.0) -> None:
        """Add a mono sound at time at, panned from -1 left to 1 right."""
        start = int(at * RATE)
        if start >= self.n or start + len(mono) <= 0:
            return
        a, b = max(start, 0), min(start + len(mono), self.n)
        piece = mono[a - start : b - start] * gain
        self.left[a:b] += piece * math.cos((pan + 1) * math.pi / 4)
        self.right[a:b] += piece * math.sin((pan + 1) * math.pi / 4)


def click(rng: np.random.Generator, pitch: float, length: float = 0.05) -> np.ndarray:
    """A soft click, a short noise burst with a pitched tick."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    burst = band_noise(n, 1500, 9000, rng) * envelope(n, 0.0005, 0.006)
    tick = np.sin(2 * np.pi * pitch * t) * envelope(n, 0.0008, 0.012)
    return burst * 0.5 + tick


def bell(freqs: list[float], length: float, decay: float, attack: float = 0.004) -> np.ndarray:
    """A soft sine bell of a few partials."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        out += np.sin(2 * np.pi * f * t) * (0.6**i)
        out += 0.25 * np.sin(2 * np.pi * f * 2.0 * t) * (0.6**i) * np.exp(-t / (decay * 0.4))
    return out * envelope(n, attack, decay) / len(freqs)


def low_tone(length: float = 0.9) -> np.ndarray:
    """The refusal, a low tone that settles."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    f = 72.0 * (1 - 0.06 * (1 - np.exp(-t / 0.15)))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    tone = np.sin(phase) + 0.45 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase)
    return tone * envelope(n, 0.012, 0.32)


def servo_track(mix: Mix, edit: dict, rec: recording.Recording, rng: np.random.Generator) -> list[tuple[float, float]]:
    """Add the whir of every joint for every arm shot, and return the spans where the arm froze for STOP."""
    fps = edit["fps"]
    whir_noise = band_noise(mix.n, 900, 4200, rng)
    freezes = []
    for item in edit["items"]:
        if item["kind"] != "shot":
            continue
        shot = json.loads((FILM / f"{item['id']}.json").read_text())
        src = shot["source"]
        t0_film = item["start"] / fps
        length = item["frames"] / fps
        times = np.arange(0, length, 1 / CONTROL)
        rec_t = src["t_start"] + times * src["speed"]
        joints = np.array([[rec.joints_at(t)[name] for name in VOICES] for t in rec_t])
        speed = np.abs(np.gradient(joints, axis=0)) * CONTROL
        n = int(length * RATE)
        audio_t = np.arange(n) / RATE
        for j, (base, pan) in enumerate(VOICES.values()):
            w = np.interp(audio_t, times, speed[:, j])
            if w.max() < 0.5:
                continue
            level = np.clip(w / 45.0, 0, 1) ** 0.75
            f = base * (1 + w / 110.0)
            phase = 2 * np.pi * np.cumsum(f) / RATE
            tone = np.sin(phase) + 0.5 * np.sin(2 * phase + 0.3) + 0.22 * np.sin(3 * phase) + 0.1 * np.sin(5 * phase)
            start = int(t0_film * RATE)
            noise = whir_noise[start : start + n] * 0.35
            voice = (tone * 0.75 + noise) * level
            mix.add(t0_film, voice, db(-19), pan)
        for e in shot["events"]:
            if e.get("path") == "/v1/stop" and e["kind"] == "request":
                freezes.append((t0_film + (e["frame"] - 1) / fps, t0_film + length))
    return freezes


def event_track(mix: Mix, edit: dict, rng: np.random.Generator) -> None:
    """Clicks, the block, the hold, approval, STOP and device connects, all on their recorded frames."""
    fps = edit["fps"]
    speed_m_s = edit["layout"]["pulse_speed_m_s"]
    for item in edit["items"]:
        if item["kind"] != "shot":
            continue
        shot = json.loads((FILM / f"{item['id']}.json").read_text())
        t0 = item["start"] / fps
        end = t0 + item["frames"] / fps

        def at(e: dict, t0: float = t0) -> float:
            return t0 + (e["frame"] - 1) / fps

        events = shot["events"]
        has_layer = "layer" in shot["set"]
        has_devices = "devices" in shot["set"]
        for e in events:
            when = at(e)
            if when < t0 - 0.05 or when > end:
                continue
            if e["source"] == "agent" and e["kind"] == "request" and has_layer:
                mix.add(when, click(rng, 2400), db(-24), -0.35)
                mix.add(when + 0.28 / speed_m_s, click(rng, 3600, 0.04), db(-30), -0.1)
            elif e.get("audit") == "action" and e.get("status") == "blocked":
                mix.add(when, low_tone(), db(-14), 0.0)
                mix.add(when, click(rng, 900, 0.06), db(-22), 0.0)
            elif e["source"] == "hub" and e["kind"] == "response" and e.get("status") == "pending":
                mix.add(when, bell([659.25, 987.77], 1.4, 0.5), db(-18), 0.1)
            elif e["source"] == "person" and str(e.get("path", "")).endswith("/approve"):
                mix.add(when, click(rng, 1800, 0.04), db(-22), 0.15)
                mix.add(when + 0.03, bell([783.99, 1174.66, 1567.98], 1.8, 0.6), db(-17), 0.1)
            elif e["source"] == "person" and e.get("path") == "/v1/stop" and e["kind"] == "request":
                mix.add(when, click(rng, 700, 0.08), db(-17), 0.0)
                thump = np.sin(2 * np.pi * 55 * np.arange(int(0.25 * RATE)) / RATE) * envelope(
                    int(0.25 * RATE), 0.002, 0.06
                )
                mix.add(when, thump, db(-15), 0.0)
            elif e.get("audit") == "register" and e.get("device") in DEVICE_NOTES and has_devices:
                mix.add(when, click(rng, 2000, 0.04), db(-28), 0.2)
            elif e.get("audit") == "connect" and e.get("device") in DEVICE_NOTES and has_devices:
                f = DEVICE_NOTES[e["device"]]
                mix.add(
                    when,
                    bell([f, f * 1.5], 1.6, 0.45),
                    db(-20),
                    {"printer": -0.3, "board": 0.4, "psu": -0.6}[e["device"]],
                )
        cues = shot.get("cues", {})
        if "layer_draw" in cues:
            a = t0 + cues["layer_draw"]["at"]
            n = int(cues["layer_draw"]["seconds"] * RATE * 1.4)
            t = np.arange(n) / RATE
            glide = 2 * np.pi * np.cumsum(330 + 330 * (t / t[-1])) / RATE
            sweep = (np.sin(glide) * 0.4 + band_noise(n, 2500, 9000, rng) * 0.25) * np.sin(np.pi * t / t[-1]) ** 2
            mix.add(a, sweep, db(-30), 0.0)


def silences(edit: dict, freezes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """From just after each STOP press to the end of the black that follows its shot."""
    fps = edit["fps"]
    out = []
    for press, shot_end in freezes:
        black = next(
            (i for i in edit["items"] if i["kind"] == "black" and abs(i["start"] / fps - shot_end) < 0.05), None
        )
        out.append((press + 0.08, (black["start"] + black["frames"]) / fps if black else shot_end))
    return out


def beds(mix: Mix, edit: dict, quiet: list[tuple[float, float]], rng: np.random.Generator) -> None:
    """Room tone that cuts out with STOP and comes back after, the cold open swell and the end card chord."""
    fps = edit["fps"]
    t = np.arange(mix.n) / RATE
    room = band_noise(mix.n, 40, 380, rng) * db(-38)
    gain = np.clip(t / 2.6, 0, 1) ** 2
    for start, end in quiet:
        gain[(t >= start) & (t < end)] = 0.0
        after = (t >= end) & (t < end + 1.2)
        gain[after] *= ((t[after] - end) / 1.2) ** 2
    mix.left += room * gain
    mix.right += np.roll(room, 2400) * gain
    n = int(3.2 * RATE)
    tt = np.arange(n) / RATE
    swell = (np.sin(2 * np.pi * 44 * tt) + 0.35 * np.sin(2 * np.pi * 88 * tt)) * np.sin(np.pi * tt / tt[-1]) ** 1.5
    mix.add(0.0, swell, db(-16), 0.0)
    card = next(i for i in edit["items"] if i["kind"] == "card")
    start = card["start"] / fps
    length = card["frames"] / fps
    n = int(length * RATE)
    tt = np.arange(n) / RATE
    chord = sum(
        np.sin(2 * np.pi * f * tt) * a
        for f, a in ((110.0, 1.0), (164.81, 0.7), (220.0, 0.6), (277.18, 0.35), (329.63, 0.3))
    )
    shape = np.clip(tt / 1.4, 0, 1) ** 2 * np.clip((length - tt) / 1.6, 0, 1)
    mix.add(start + 0.25, chord * shape, db(-22), 0.0)


def note(name: str) -> float:
    """Equal-tempered frequency of a note name such as A2, C#3 or Bb4."""
    accidental = name[1:-1]
    steps = SEMITONES[name[0]] + accidental.count("#") - accidental.count("b") + 12 * (int(name[-1]) - 4)
    return 440.0 * 2 ** (steps / 12)


def pad(freqs: list[float], length: float, attack: float, release: float) -> np.ndarray:
    """A soft chord of slightly detuned sines that swells in over attack and fades out over release."""
    n = int((length + release) * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        weight = 1.0 / (1.0 + 0.3 * i)
        for j, cents in enumerate((-4.0, 0.0, 4.0)):
            phase = 2 * np.pi * f * 2 ** (cents / 1200) * t + 1.7 * i + 0.9 * j
            out += weight * (np.sin(phase) + 0.16 * np.sin(2 * phase) + 0.05 * np.sin(3 * phase))
    rise = 0.5 - 0.5 * np.cos(np.pi * np.clip(t / max(attack, 1e-3), 0, 1))
    fall = 0.5 - 0.5 * np.cos(np.pi * np.clip((length + release - t) / max(release, 1e-3), 0, 1))
    breath = 1.0 + 0.08 * np.sin(2 * np.pi * 0.12 * t)
    return out * rise * fall * breath / (3 * len(freqs))


def pluck(freq: float, length: float = 0.8) -> np.ndarray:
    """A short, clean FM pluck whose brightness falls away in the first 50 ms."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    index = 1.4 * np.exp(-t / 0.05)
    return np.sin(2 * np.pi * freq * t + index * np.sin(2 * np.pi * 2 * freq * t)) * envelope(n, 0.002, 0.17)


def tock(freq: float, rng: np.random.Generator) -> np.ndarray:
    """A low, short knock with a faint tick on top, for a cut."""
    n = int(0.3 * RATE)
    t = np.arange(n) / RATE
    f = freq * (1 + 0.6 * np.exp(-t / 0.012))
    body = np.sin(2 * np.pi * np.cumsum(f) / RATE) * envelope(n, 0.001, 0.07)
    return body + 0.2 * band_noise(n, 4000, 10000, rng) * envelope(n, 0.0003, 0.004)


def reverb(mono: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """The wet left and right of a small, dark room around a mono signal, from two noise tails convolved by FFT."""
    n_ir = int(2.4 * RATE)
    t = np.arange(n_ir) / RATE
    shape = np.exp(-t / 0.38) * np.clip(t / 0.012, 0, 1)
    size = 1 << int(np.ceil(np.log2(len(mono) + n_ir)))
    dry = np.fft.rfft(mono, size)
    out = []
    for _ in range(2):
        ir = band_noise(n_ir, 180, 5200, rng) * shape
        ir /= np.sqrt(np.sum(ir**2))
        out.append(np.fft.irfft(dry * np.fft.rfft(ir, size), size)[: len(mono)])
    return out[0], out[1]


def beats(edit: dict) -> dict[int, tuple[float, float]]:
    """Start and end of every storyboard beat in the edit, in film seconds."""
    fps = edit["fps"]
    spans: dict[int, tuple[float, float]] = {}
    for item in edit["items"]:
        if "storyboard" not in item:
            continue
        a, b = item["start"] / fps, (item["start"] + item["frames"]) / fps
        lo, hi = spans.get(item["storyboard"], (a, b))
        spans[item["storyboard"]] = (min(lo, a), max(hi, b))
    return spans


def bed_cues(edit: dict) -> list[tuple[float, float]]:
    """Film times of the cues the bed dips under, with how far it dips, in dB."""
    fps = edit["fps"]
    cues = []
    for item in edit["items"]:
        if item["kind"] != "shot":
            continue
        shot = json.loads((FILM / f"{item['id']}.json").read_text())
        t0 = item["start"] / fps
        has_devices = "devices" in shot["set"]
        for e in shot["events"]:
            when = t0 + (e["frame"] - 1) / fps
            if when < t0 - 0.05 or when > t0 + item["frames"] / fps:
                continue
            held = e["source"] == "hub" and e["kind"] == "response" and e.get("status") == "pending"
            approved = e["source"] == "person" and str(e.get("path", "")).endswith("/approve")
            if e.get("audit") == "action" and e.get("status") == "blocked":
                cues.append((when, 9.0))
            elif held or approved:
                cues.append((when, 5.0))
            elif e.get("audit") == "connect" and e.get("device") in DEVICE_NOTES and has_devices:
                cues.append((when, 3.0))
    return cues


def music_bed(edit: dict, gates: list[tuple[float, float]], n: int) -> tuple[np.ndarray, np.ndarray]:
    """The music bed, n samples long, silent inside every gate span."""
    rng = np.random.default_rng(SEED + 1)
    fps = edit["fps"]
    spans = beats(edit)
    mono = np.zeros(n)
    left, right = np.zeros(n), np.zeros(n)

    def place(buf: np.ndarray, at: float, sound: np.ndarray, gain: float) -> None:
        start = int(at * RATE)
        end = min(start + len(sound), n)
        if start < n:
            buf[start:end] += sound[: end - start] * gain

    reentry = {round(b, 3) for _, b in gates}
    end_of_film = edit["frames"] / fps
    for beat, (start, end) in spans.items():
        chord, steps = BED[beat]
        freqs = [note(name) for name in chord]
        if beat == 1:
            attack, release, length = 2.4, 0.3, end - start
        elif beat == max(spans):
            attack, release, length = 0.3, 2.2, end_of_film - start - 2.2
        else:
            attack, release, length = (0.35 if round(start, 3) in reentry else 0.12), 0.3, end - start
        trim = db(BED_TRIM_DB.get(beat, 0.0))
        place(mono, start, pad(freqs, length, attack, release), trim)
        first = start + (3.0 if beat == 1 else 0.0)
        last = start + 3.6 if beat == max(spans) else end
        every = PLUCK_EVERY[beat] * STEP_S
        k = 0
        at = first
        while at < last - 0.05:
            sound = pluck(note(steps[k % len(steps)]))
            gain = (0.32 if k % 4 == 0 else 0.24) * trim
            pan = -0.3 if k % 2 == 0 else 0.3
            place(left, at, sound, gain * math.cos((pan + 1) * math.pi / 4))
            place(right, at, sound, gain * math.sin((pan + 1) * math.pi / 4))
            k += 1
            at = first + k * every
    beat_starts = {round(a, 3) for a, _ in spans.values()}
    for item in edit["items"]:
        at = item["start"] / fps
        if item["kind"] == "shot" and round(at, 3) not in beat_starts:
            beat = item.get("storyboard", 1)
            place(mono, at, tock(note(BED[beat][0][0]) * 2, rng), 0.5)
    wet_l, wet_r = reverb(mono + 0.5 * (left + right), rng)
    left = mono + left + 0.24 * wet_l
    right = mono + right + 0.24 * wet_r
    t = np.arange(n) / RATE
    duck = np.zeros(n)
    for when, depth in bed_cues(edit):
        shape = np.clip((t - when + 0.02) / 0.02, 0, 1) * np.exp(-np.maximum(t - when - 0.25, 0) / 0.45)
        duck = np.maximum(duck, depth * shape)
    gain = 10 ** (-duck / 20)
    for press, back in gates:
        gain[(t >= press) & (t < back)] = 0.0
        ramp = (t >= press - 0.004) & (t < press)
        gain[ramp] *= (press - t[ramp]) / 0.004
    return left * gain, right * gain


def write_wav(path: Path, left: np.ndarray, right: np.ndarray) -> None:
    """48 kHz, 24-bit stereo PCM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.stack([left, right], axis=1)
    ints = np.clip(np.round(data * (2**23 - 1)), -(2**23), 2**23 - 1).astype("<i4")
    raw = ints.reshape(-1).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(RATE)
        handle.writeframes(raw)


def read_music(path: Path, n: int) -> tuple[np.ndarray, np.ndarray]:
    """A 48 kHz 16 or 24-bit PCM WAV as two float channels, cut or padded to n samples."""
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != RATE:
            raise SystemExit(f"{path} must be {RATE} Hz PCM, convert it with ffmpeg first")
        width, channels = handle.getsampwidth(), handle.getnchannels()
        raw = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.uint8)
    if width == 2:
        samples = raw.view("<i2").astype(np.float64) / 2**15
    elif width == 3:
        padded = np.zeros((len(raw) // 3, 4), dtype=np.uint8)
        padded[:, 1:] = raw.reshape(-1, 3)
        samples = padded.view("<i4").reshape(-1).astype(np.float64) / 2**31
    else:
        raise SystemExit(f"{path} must be 16 or 24-bit PCM")
    samples = samples.reshape(-1, channels)
    left = samples[:, 0]
    right = samples[:, 1] if channels > 1 else samples[:, 0]
    out_l, out_r = np.zeros(n), np.zeros(n)
    m = min(n, len(left))
    out_l[:m], out_r[:m] = left[:m], right[:m]
    return out_l, out_r


def main() -> int:
    """Write the effects mix, with the music slot filled when --music is given."""
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--music", default="", help="optional 48 kHz PCM WAV that replaces the music bed")
    p.add_argument("--music-db", type=float, default=-16.0)
    p.add_argument("--bed-db", type=float, default=BED_DB)
    p.add_argument("--no-bed", action="store_true")
    opts = p.parse_args()
    edit = json.loads((FILM / "edit.json").read_text())
    rec = recording.load()
    rng = np.random.default_rng(SEED)
    mix = Mix(edit["frames"] / edit["fps"])
    freezes = servo_track(mix, edit, rec, rng)
    event_track(mix, edit, rng)
    quiet = silences(edit, freezes)
    t = np.arange(mix.n) / RATE
    for a, b in quiet:
        cut = (t >= a) & (t < b)
        mix.left[cut] = 0.0
        mix.right[cut] = 0.0
    beds(mix, edit, quiet, rng)
    if opts.music:
        music_l, music_r = read_music(Path(opts.music), mix.n)
        duck = np.ones(mix.n)
        for a, b in quiet:
            duck[(t >= a) & (t < b)] = 0.0
        mix.left += music_l * db(opts.music_db) * duck
        mix.right += music_r * db(opts.music_db) * duck
    elif not opts.no_bed:
        gates = [(press, back) for (press, _), (_, back) in zip(freezes, quiet, strict=True)]
        bed_l, bed_r = music_bed(edit, gates, mix.n)
        mix.left += bed_l * db(opts.bed_db)
        mix.right += bed_r * db(opts.bed_db)
    length = int(edit["frames"] / edit["fps"] * RATE)
    left = np.tanh(mix.left[:length] * 1.4) / 1.4
    right = np.tanh(mix.right[:length] * 1.4) / 1.4
    write_wav(Path(opts.out), left, right)
    print(f"wrote {opts.out}, {length / RATE:.2f} s, peak {max(np.abs(left).max(), np.abs(right).max()):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
