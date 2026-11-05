"""A simulated four channel bench oscilloscope with a built-in waveform generator, answering SCPI.

The bench it models. The generator's output drives a small test board, an RC low-pass filter of
1 kOhm and 100 nF, and the passive probe on channel 1 hooks onto the filter's output, so a square
wave arrives with rounded edges and a sine arrives smaller and later. Channels 2 to 4 have nothing
connected. `ScpiServer(BenchScope())` serves it through real PyVISA, and a device file reaches the
shared one in its process with `resource: sim:scope`.

The scope starts the way someone left it, at 5 V a division and 50 ms a division with the trigger
level above the signal, so the signal has to be found. `*RST` gives the factory settings instead.

Commands, in short or long form and any case.

    *IDN?  *OPC?  *RST  *CLS  :SYST:ERR?
    :CHAN<n>:DISP  :CHAN<n>:SCAL  :CHAN<n>:OFFS      on or off, volts a division, volts
    :TIM:SCAL  :TIM:POS                              seconds a division, the trigger point's offset
    :TRIG:EDGE:SOUR  :TRIG:EDGE:LEV  :TRIG:EDGE:SLOP  :TRIG:SWE AUTO|NORM|SING  :TRIG:STAT?
    :RUN  :STOP  :SING
    :MEAS:FREQ?  :MEAS:PER?  :MEAS:VPP?  :MEAS:VMAX?  :MEAS:VMIN?  :MEAS:VAVG?  :MEAS:VRMS?  :MEAS:RIS?  :MEAS:FALL?
    :WAV:SOUR  :WAV:FORM ASC|BYTE  :WAV:POIN?  :WAV:PRE?  :WAV:DATA?
    :DISP:DATA? PNG                                  the screen as a PNG in a definite-length block
    :SOUR:FUNC SIN|SQU  :SOUR:FREQ  :SOUR:VOLT  :SOUR:VOLT:OFFS  :OUTP

Measurements run on the 1000-point screen record, through an 8-bit converter spanning 10
divisions. A measurement the record can't support returns 9.9E37, SCPI's code for an invalid
value. That happens with less than one cycle or fewer than 8 points a cycle on screen, with a
trace past the top or bottom of the screen, or with less than half a division of signal to time.
"""

from __future__ import annotations

import math
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.scpi.simulator import LONG_FORMS, canonical

FORMS = {
    **LONG_FORMS,
    **{word: word[:4] for word in ("CHANNEL", "DISPLAY", "SCALE", "OFFSET", "SLOPE", "FORMAT", "POINTS")},
    **{"LEVEL": "LEV", "POSITIVE": "POS", "NEGATIVE": "NEG"},
    **{"TIMEBASE": "TIM", "POSITION": "POS", "TRIGGER": "TRIG", "SWEEP": "SWE", "STATUS": "STAT", "RISE": "RIS"},
    **{"MEASURE": "MEAS", "FREQUENCY": "FREQ", "PERIOD": "PER", "WAVEFORM": "WAV", "PREAMBLE": "PRE"},
    **{"FUNCTION": "FUNC", "SINGLE": "SING", "SQUARE": "SQU", "SINUSOID": "SIN", "ASCII": "ASC", "NORMAL": "NORM"},
}
POINTS = 1000
COLUMNS, ROWS = 10, 8
CODES_PER_DIV = 25.6
INVALID = 9.9e37
TAU_S = 1e3 * 100e-9
NOISE_V = 0.0015
CHANNELS = (1, 2, 3, 4)
SCALES = (0.001, 10.0)
TIMEBASES = (5e-9, 50.0)
GEN_AMPLITUDE = (0.01, 5.0)
GEN_FREQUENCY = (0.1, 25e6)
GEN_OFFSET = 2.5
TIMING = ("FREQ", "PER", "RIS", "FALL")
MEASUREMENTS = ("FREQ", "PER", "VPP", "VMAX", "VMIN", "VAVG", "VRMS", "RIS", "FALL")


@dataclass
class Channel:
    shown: bool
    scale: float = 1.0
    offset: float = 0.0


@dataclass
class Generator:
    function: str = "SQU"
    frequency: float = 1000.0
    amplitude: float = 1.0
    offset: float = 0.0
    output: bool = True


@dataclass
class Trace:
    """One channel's screen record in volts, with each point's low and high in divisions for drawing."""

    volts: list[float]
    lows: list[float]
    highs: list[float]


@dataclass
class Acquisition:
    at: float
    status: str
    traces: dict[int, Trace] = field(default_factory=dict)


def block(data: bytes) -> bytes:
    """An IEEE 488.2 definite-length block."""
    size = str(len(data))
    return f"#{len(size)}{size}".encode("ascii") + data


def _source(text: str) -> int | None:
    match = re.fullmatch(r"CHAN(?:NEL)?([1-4])", text.strip().upper())
    return int(match.group(1)) if match else None


class BenchScope:
    """The instrument and its SCPI answers. Thread safe."""

    idn = "OpenHAL,SIM-SCOPE-4,SIM00000001,0.1.0"

    def __init__(self, clock: Callable[[], float] = time.monotonic, seed: int = 7) -> None:
        self.clock = clock
        self.seed = seed
        self.lock = threading.RLock()
        self.errors: list[str] = []
        self.commands: list[str] = []
        self.generator = Generator()
        self._factory()
        self.channels[1].scale = 5.0
        self.timebase = 0.05
        self.trigger_level = 3.0

    def _factory(self) -> None:
        self.channels = {n: Channel(shown=n == 1) for n in CHANNELS}
        self.timebase, self.position = 0.001, 0.0
        self.trigger_source, self.trigger_level, self.trigger_slope = 1, 0.0, "POS"
        self.sweep, self.running, self.single = "AUTO", True, False
        self.wave_source, self.wave_format = 1, "ASC"
        self.readouts: list[tuple[str, int]] = []
        self._last: Acquisition | None = None
        self._changed = True

    def _error(self, text: str) -> None:
        if len(self.errors) < 20:
            self.errors.append(text)

    def volts(self, channel: int, t: float) -> float:
        """The voltage at a channel's input at time t, in seconds."""
        g = self.generator
        if channel != 1 or not g.output:
            return 0.0
        omega = 2 * math.pi * g.frequency
        if g.function == "SIN":
            gain = 1 / math.sqrt(1 + (omega * TAU_S) ** 2)
            return g.offset + g.amplitude / 2 * gain * math.sin(omega * t - math.atan(omega * TAU_S))
        period = 1 / g.frequency
        half, phase, high = period / 2, t % period, g.amplitude / 2
        start = high * math.tanh(half / (2 * TAU_S))
        if phase < half:
            return g.offset + high - (high + start) * math.exp(-phase / TAU_S)
        return g.offset - high + (high + start) * math.exp(-(phase - half) / TAU_S)

    def _trigger_time(self) -> float | None:
        """A time within one period where the trigger source crosses the level on the trigger's slope."""
        g = self.generator
        if self.trigger_source != 1 or not g.output:
            return None
        period, steps, level = 1 / g.frequency, 400, self.trigger_level
        before = self.volts(1, 0.0)
        for step in range(1, steps + 1):
            t = period * step / steps
            now = self.volts(1, t)
            rising, falling = before < level <= now, before > level >= now
            if (rising and self.trigger_slope == "POS") or (falling and self.trigger_slope == "NEG"):
                return t - period / steps * (now - level) / (now - before)
            before = now
        return None

    def acquire(self, at: float | None = None) -> Acquisition:
        """The screen's current acquisition, a new one while running, the last one when stopped or waiting."""
        with self.lock:
            at = self.clock() if at is None else at
            last = self._last
            if last is not None and (not self.running or (not self._changed and 0 <= at - last.at < 0.02)):
                return last
            self._changed = False
            found = self._trigger_time()
            if found is None and (self.sweep == "NORM" or self.single) and last is not None:
                self._last = Acquisition(at, "WAIT", last.traces)
                return self._last
            period = 1 / self.generator.frequency
            zero = found if found is not None else (at * 13.37 + 0.21) % 1 * period
            status = "TD" if found is not None else ("AUTO" if self.sweep == "AUTO" and not self.single else "WAIT")
            self._last = Acquisition(at, status, self._record(zero, at))
            if self.single and found is not None:
                self.single, self.running = False, False
                self._last.status = "STOP"
            return self._last

    def _record(self, zero: float, at: float) -> dict[int, Trace]:
        span = COLUMNS * self.timebase
        dt = span / POINTS
        start = zero + self.position - span / 2
        noise = random.Random(self.seed * 1_000_003 + int(at * 1000))  # noqa: S311 (simulated noise)
        dense = 1 / self.generator.frequency < 8 * dt
        traces = {}
        for n, channel in self.channels.items():
            if not channel.shown:
                continue
            volts, lows, highs = [], [], []
            for i in range(POINTS):
                t = start + i * dt
                value = self.volts(n, t) + noise.gauss(0, NOISE_V)
                volts.append(self._quantize(n, value))
                spread = [value] + ([self.volts(n, t + dt * k / 6) for k in range(1, 6)] if dense else [])
                lows.append(self._code(n, min(spread)) / CODES_PER_DIV)
                highs.append(self._code(n, max(spread)) / CODES_PER_DIV)
            traces[n] = Trace(volts, lows, highs)
        return traces

    def _code(self, n: int, value: float) -> int:
        channel = self.channels[n]
        return max(-128, min(127, round((value + channel.offset) / channel.scale * CODES_PER_DIV)))

    def _quantize(self, n: int, value: float) -> float:
        channel = self.channels[n]
        return self._code(n, value) / CODES_PER_DIV * channel.scale - channel.offset

    def measure(self, item: str, n: int, acquisition: Acquisition | None = None) -> float:
        """One measurement on a channel's screen record, or INVALID."""
        with self.lock:
            trace = (acquisition or self.acquire()).traces.get(n)
            if trace is None:
                return INVALID
            channel, values = self.channels[n], trace.volts
            high = max(trace.highs) * channel.scale - channel.offset
            low = min(trace.lows) * channel.scale - channel.offset
            clipped = max(trace.highs) > ROWS / 2 or min(trace.lows) < -ROWS / 2
            if item not in TIMING:
                if clipped:
                    return INVALID
                mean = sum(values) / len(values)
                rms = math.sqrt(sum(v * v for v in values) / len(values))
                return {"VPP": high - low, "VMAX": high, "VMIN": low, "VAVG": mean, "VRMS": rms}[item]
            if (high - low) / channel.scale < 0.5:
                return INVALID
            return self._timing(item, values, max(values), min(values))

    def _timing(self, item: str, values: list[float], high: float, low: float) -> float:
        dt = COLUMNS * self.timebase / POINTS
        mid, band = (high + low) / 2, (high - low) * 0.1
        rising, falling, state = [], [], values[0] >= mid + band
        for i in range(1, len(values)):
            if not state and values[i] >= mid + band:
                state = True
                rising.append(i)
            elif state and values[i] <= mid - band:
                state = False
                falling.append(i)
        if len(rising) < 2:
            return INVALID
        period = (rising[-1] - rising[0]) / (len(rising) - 1) * dt
        if period / dt < 8:
            return INVALID
        if item == "FREQ":
            return 1 / period
        if item == "PER":
            return period
        up = item == "RIS"
        ten, ninety = low + 0.1 * (high - low), low + 0.9 * (high - low)
        first, last = (ten, ninety) if up else (ninety, ten)
        for middle in rising if up else falling:
            before = next((i for i in range(middle, 0, -1) if (values[i] <= first) == up), None)
            after = next((i for i in range(middle, len(values)) if (values[i] >= last) == up), None)
            if before is not None and after is not None and after - before >= 3:
                return (after - before) * dt
        return INVALID

    def snapshot(self, at: float | None = None) -> dict[str, Any]:
        """Everything the screen shows, for drawing it or recording it."""
        with self.lock:
            acquisition = self.acquire(at)
            return {
                "status": "STOP" if not self.running else acquisition.status,
                "timebase": self.timebase,
                "position": self.position,
                "trigger": {"source": self.trigger_source, "level": self.trigger_level, "slope": self.trigger_slope},
                "channels": {
                    n: {"shown": c.shown, "scale": c.scale, "offset": c.offset} for n, c in self.channels.items()
                },
                "generator": vars(self.generator).copy(),
                "measurements": [
                    {"item": item, "source": n, "value": self.measure(item, n, acquisition)}
                    for item, n in self.readouts
                ],
                "traces": {n: {"lows": t.lows, "highs": t.highs} for n, t in acquisition.traces.items()},
            }

    def answer(self, line: str) -> str | bytes | None:
        with self.lock:
            self.commands.append(line)
            replies = []
            for part in (item.strip() for item in line.split(";")):
                if part:
                    replies.append(self._one(part))
                    self._changed = self._changed or not part.partition(" ")[0].endswith("?")
            found = [reply for reply in replies if reply is not None]
            if len(found) == 1 and isinstance(found[0], bytes):
                return found[0]
            return ";".join(str(reply) for reply in found) if found else None

    def _one(self, command: str) -> str | bytes | None:
        header, _, rest = command.partition(" ")
        head = canonical(header, FORMS)
        args = [item.strip() for item in rest.split(",")] if rest else []
        fixed: dict[str, Callable[[], str | bytes | None]] = {
            "*IDN?": lambda: self.idn,
            "*OPC?": lambda: "1",
            "*RST": self._factory,
            "*CLS": self.errors.clear,
            "SYST:ERR?": lambda: self.errors.pop(0) if self.errors else '0,"No error"',
            "RUN": lambda: self._run(True),
            "STOP": lambda: self._run(False),
            "SING": self._arm,
            "TRIG:STAT?": lambda: self.snapshot()["status"],
            "WAV:POIN?": lambda: str(POINTS),
            "WAV:PRE?": self._preamble,
            "WAV:DATA?": self._data,
        }
        if head in fixed:
            return fixed[head]()
        if head == "DISP:DATA?":
            if args and args[0].upper() != "PNG":
                self._error('-224,"Illegal parameter value"')
                return None
            from openhal.drivers.scpi import screen

            return block(screen.render(self.snapshot()))
        measured = re.fullmatch(r"MEAS:([A-Z]+)\?", head)
        if measured and measured.group(1) in MEASUREMENTS:
            n = _source(args[0]) if args else 1
            if n is None:
                self._error('-224,"Illegal parameter value"')
                return f"{INVALID:.5E}"
            if (measured.group(1), n) not in self.readouts:
                self.readouts = [*self.readouts, (measured.group(1), n)][-4:]
            return f"{self.measure(measured.group(1), n):.5E}"
        return self._setting(head, args)

    def _run(self, on: bool) -> None:
        self.running, self.single = on, False

    def _arm(self) -> None:
        self.running, self.single = True, True

    def _setting(self, head: str, args: list[str]) -> str | None:
        query = head.endswith("?")
        word = args[0] if args else ""
        chan = re.fullmatch(r"CHAN([1-4]):(DISP|SCAL|OFFS)\??", head)
        if chan:
            channel = self.channels[int(chan.group(1))]
            attr = {"DISP": "shown", "SCAL": "scale", "OFFS": "offset"}[chan.group(2)]
            limits = {"SCAL": SCALES, "OFFS": (-20 * channel.scale, 20 * channel.scale)}.get(chan.group(2))
            return self._value(channel, attr, query, word, limits)
        targets: dict[str, tuple[Any, str, tuple[float, float] | None]] = {
            "TIM:SCAL": (self, "timebase", TIMEBASES),
            "TIM:POS": (self, "position", (-500 * self.timebase, 500 * self.timebase)),
            "TRIG:EDGE:LEV": (self, "trigger_level", (-40.0, 40.0)),
            "SOUR:FREQ": (self.generator, "frequency", GEN_FREQUENCY),
            "SOUR:VOLT": (self.generator, "amplitude", GEN_AMPLITUDE),
            "SOUR:VOLT:OFFS": (self.generator, "offset", (-GEN_OFFSET, GEN_OFFSET)),
            "OUTP": (self.generator, "output", None),
        }
        if head.rstrip("?") in targets:
            target, attr, limits = targets[head.rstrip("?")]
            return self._value(target, attr, query, word, limits)
        words: dict[str, tuple[Any, str, tuple[str, ...]]] = {
            "TRIG:EDGE:SLOP": (self, "trigger_slope", ("POS", "NEG")),
            "TRIG:SWE": (self, "sweep", ("AUTO", "NORM", "SING")),
            "SOUR:FUNC": (self.generator, "function", ("SIN", "SQU")),
            "WAV:FORM": (self, "wave_format", ("ASC", "BYTE")),
        }
        if head.rstrip("?") in words:
            target, attr, allowed = words[head.rstrip("?")]
            if query:
                return str(getattr(target, attr))
            choice = canonical(word, FORMS) if word else ""
            if choice not in allowed:
                self._error('-224,"Illegal parameter value"')
                return None
            if attr == "sweep" and choice == "SING":
                self._arm()
            else:
                setattr(target, attr, choice)
            return None
        if head.rstrip("?") in ("TRIG:EDGE:SOUR", "WAV:SOUR"):
            attr = "trigger_source" if head.startswith("TRIG") else "wave_source"
            if query:
                return f"CHAN{getattr(self, attr)}"
            n = _source(word)
            if n is None:
                self._error('-224,"Illegal parameter value"')
            else:
                setattr(self, attr, n)
            return None
        self._error('-113,"Undefined header"')
        return None

    def _value(self, target: Any, attr: str, query: bool, word: str, limits: tuple[float, float] | None) -> str | None:
        current = getattr(target, attr)
        if query:
            return ("1" if current else "0") if isinstance(current, bool) else f"{current:.5E}"
        if isinstance(current, bool):
            if word.upper() not in ("ON", "OFF", "1", "0"):
                self._error('-224,"Illegal parameter value"')
                return None
            setattr(target, attr, word.upper() in ("ON", "1"))
            return None
        try:
            value = float(word)
        except ValueError:
            self._error('-109,"Missing parameter"' if not word else '-224,"Illegal parameter value"')
            return None
        if limits and not limits[0] <= value <= limits[1]:
            self._error('-222,"Data out of range"')
            return None
        setattr(target, attr, value)
        return None

    def _preamble(self) -> str:
        channel = self.channels[self.wave_source]
        xinc = COLUMNS * self.timebase / POINTS
        form = 2 if self.wave_format == "ASC" else 0
        yinc = channel.scale / CODES_PER_DIV
        origin = self.position - POINTS / 2 * xinc
        return f"{form},0,{POINTS},1,{xinc:.6E},{origin:.6E},0,{yinc:.6E},{-channel.offset:.6E},128"

    def _data(self) -> str | bytes | None:
        trace = self.acquire().traces.get(self.wave_source)
        if trace is None:
            self._error('-221,"Settings conflict"')
            return None
        if self.wave_format == "ASC":
            return ",".join(f"{v:.5E}" for v in trace.volts)
        channel = self.channels[self.wave_source]
        codes = (round((v + channel.offset) / channel.scale * CODES_PER_DIV) + 128 for v in trace.volts)
        return block(bytes(max(0, min(255, code)) for code in codes))
