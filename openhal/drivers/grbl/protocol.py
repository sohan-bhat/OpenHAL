"""GRBL 1.1 line protocol helpers. Parsing and formatting only, no I/O.

Written from the GRBL 1.1 interface documentation (github.com/gnea/grbl/wiki, "Grbl v1.1
Interface", "Grbl v1.1 Commands" and the error and alarm code tables). The messages below are
paraphrased, not copied, because GRBL itself is GPL-3.0.

Message shapes the controller sends.

    ok                                       a line command finished parsing
    error:N                                  a line command was refused
    ALARM:N                                  the controller entered the alarm state
    <Idle|MPos:0.000,0.000,0.000|FS:0,0>     a status report, the answer to the `?` byte
    [MSG:...] [GC:...] [VER:...] [G54:...]   feedback in square brackets
    $N=value                                 one setting, part of the `$$` answer
    Grbl 1.1h ['$' for help]                 the banner after a power-up or soft reset
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Final

STATUS_QUERY: Final = b"?"
FEED_HOLD: Final = b"!"
CYCLE_START: Final = b"~"
SOFT_RESET: Final = b"\x18"
JOG_CANCEL: Final = b"\x85"

STATES: Final = ("idle", "run", "hold", "jog", "alarm", "door", "check", "home", "sleep")
AXES: Final = ("x", "y", "z", "a")
BANNER: Final = re.compile(r"^Grbl(?:HAL)?\s+(\S+)\s+\[", re.IGNORECASE)
SETTING: Final = re.compile(r"^\$(\d{1,3})=(\S*)")
BRACKET: Final = re.compile(r"^\[([A-Z0-9.]+):(.*)\]$")

ERRORS: Final[dict[int, str]] = {
    1: "a G-code word has no letter",
    2: "a G-code word has no value or a badly formed number",
    3: "the $ command is not recognized",
    4: "a value that must be positive is negative",
    5: "homing is not enabled in the settings ($22)",
    6: "the step pulse must be longer than 3 microseconds",
    7: "the EEPROM read failed and defaults were restored",
    8: "this $ command only works while the machine is idle",
    9: "G-code is locked out while the machine is in alarm or jogging",
    10: "soft limits need homing to be enabled",
    11: "the line is longer than the controller accepts",
    12: "the setting would push the step rate past the maximum",
    13: "the safety door is open",
    14: "the startup or build line is too long to store",
    15: "the jog target is outside the machine travel",
    16: "the jog command is malformed or uses a word that is not allowed",
    17: "laser mode needs PWM spindle output",
    20: "the G-code command is not supported",
    21: "two commands from the same modal group are in one line",
    22: "no feed rate has been set",
    23: "a command needs an integer value",
    24: "two commands in one line both need axis words",
    25: "a word is repeated in the line",
    26: "the command needs axis words and none were given",
    27: "the line number is invalid",
    28: "a required value word is missing",
    29: "G59.x work coordinate systems are not supported",
    30: "G53 only works with G0 and G1",
    31: "axis words were given but nothing uses them",
    32: "an arc needs at least one axis word in its plane",
    33: "the motion target is invalid",
    34: "the arc radius is invalid",
    35: "an arc needs at least one offset word in its plane",
    36: "the line has value words nothing uses",
    37: "the tool length offset is not on the configured axis",
    38: "the tool number is larger than supported",
}

ALARMS: Final[dict[int, str]] = {
    1: "a hard limit switch triggered, position is probably lost, home again",
    2: "a motion target was outside the machine travel, position was kept",
    3: "reset while moving, position may be lost, home again",
    4: "the probe was not in its expected state before probing",
    5: "the probe did not touch anything within the programmed travel",
    6: "homing was interrupted by a reset",
    7: "homing was interrupted because the safety door opened",
    8: "homing could not pull off the limit switch, check pull-off and wiring",
    9: "homing could not find the limit switch within the search distance",
    10: "homing could not find the second switch of a dual axis",
}

SETTING_UNITS: Final[dict[int, str]] = {
    0: "us",
    1: "ms",
    11: "mm",
    12: "mm",
    24: "mm/min",
    25: "mm/min",
    26: "ms",
    27: "mm",
    30: "rpm",
    31: "rpm",
    **{100 + axis: "1/mm" for axis in range(4)},
    **{110 + axis: "mm/min" for axis in range(4)},
    **{120 + axis: "mm/s**2" for axis in range(4)},
    **{130 + axis: "mm" for axis in range(4)},
}
"""The unit of each numeric setting. Settings stay in millimeters even when $13 reports inches."""


def error_text(code: int) -> str:
    return ERRORS.get(code, "an error code this driver does not know")


def alarm_text(code: int) -> str:
    return ALARMS.get(code, "an alarm code this driver does not know")


@dataclass(frozen=True, slots=True)
class Status:
    """One parsed status report. Positions are in the report's units (mm, or inch with $13=1)."""

    state: str
    substate: int | None = None
    mpos: tuple[float, ...] | None = None
    wpos: tuple[float, ...] | None = None
    wco: tuple[float, ...] | None = None
    feed: float | None = None
    spindle: float | None = None
    pins: str = ""
    overrides: tuple[int, int, int] | None = None
    accessories: str | None = None
    buffer: tuple[int, int] | None = None
    line: int | None = None
    raw: str = field(default="", compare=False)


def _numbers(text: str, what: str) -> tuple[float, ...]:
    try:
        values = tuple(float(item) for item in text.split(","))
    except ValueError:
        raise ValueError(f"{what} has a value that is not a number ({text!r})") from None
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{what} is not finite ({text!r})")
    return values


def parse_status(line: str) -> Status:
    """Parse `<State|Field:value|...>`. Raises ValueError for anything malformed."""
    if not (line.startswith("<") and line.endswith(">")) or len(line) > 512:
        raise ValueError(f"not a status report: {line!r}")
    parts = line[1:-1].split("|")
    head, _, sub = parts[0].partition(":")
    state = head.lower()
    if state not in STATES:
        raise ValueError(f"unknown machine state {head!r}")
    values: dict[str, object] = {"state": state, "raw": line}
    if sub:
        if not sub.isdigit():
            raise ValueError(f"bad substate in {parts[0]!r}")
        values["substate"] = int(sub)
    for part in parts[1:]:
        key, sep, body = part.partition(":")
        if not sep:
            raise ValueError(f"status field {part!r} has no value")
        if key in ("MPos", "WPos", "WCO"):
            values[key.lower()] = _numbers(body, key)
        elif key == "FS":
            numbers = _numbers(body, key)
            if len(numbers) != 2:
                raise ValueError(f"FS needs feed and speed, got {body!r}")
            values["feed"], values["spindle"] = numbers
        elif key == "F":
            values["feed"] = _numbers(body, key)[0]
        elif key == "Ov":
            numbers = _numbers(body, key)
            if len(numbers) != 3:
                raise ValueError(f"Ov needs three values, got {body!r}")
            values["overrides"] = (int(numbers[0]), int(numbers[1]), int(numbers[2]))
        elif key == "Bf":
            numbers = _numbers(body, key)
            if len(numbers) != 2:
                raise ValueError(f"Bf needs two values, got {body!r}")
            values["buffer"] = (int(numbers[0]), int(numbers[1]))
        elif key == "Ln":
            values["line"] = int(_numbers(body, key)[0])
        elif key == "Pn":
            values["pins"] = body
        elif key == "A":
            values["accessories"] = body
    if "mpos" not in values and "wpos" not in values:
        raise ValueError(f"status report has no position: {line!r}")
    return Status(**values)  # type: ignore[arg-type]


def parse_bracket(line: str) -> tuple[str, str] | None:
    """`[GC:G0 G54]` becomes ("GC", "G0 G54"). Anything else is None."""
    match = BRACKET.match(line)
    return (match.group(1), match.group(2)) if match else None


def parse_setting(line: str) -> tuple[int, str] | None:
    match = SETTING.match(line)
    return (int(match.group(1)), match.group(2)) if match else None


def parse_modes(body: str) -> dict[str, str | float]:
    """The `$G` parser state. Keys are motion, wcs, plane, units, distance, spindle, coolant, tool, feed, speed."""
    modes: dict[str, str | float] = {}
    coolant: list[str] = []
    for word in body.split():
        letter, number = word[:1], word[1:]
        if letter == "M" and number in ("7", "8", "9"):
            coolant.append(word)
        elif letter == "M" and number in ("3", "4", "5"):
            modes["spindle"] = word
        elif letter == "M":
            modes["program"] = word
        elif word in ("G0", "G1", "G2", "G3", "G38.2", "G38.3", "G38.4", "G38.5", "G80"):
            modes["motion"] = word
        elif word in ("G54", "G55", "G56", "G57", "G58", "G59"):
            modes["wcs"] = word
        elif word in ("G17", "G18", "G19"):
            modes["plane"] = word
        elif word in ("G20", "G21"):
            modes["units"] = word
        elif word in ("G90", "G91"):
            modes["distance"] = word
        elif letter == "T":
            modes["tool"] = word
        elif letter in ("F", "S"):
            try:
                modes["feed" if letter == "F" else "speed"] = float(number)
            except ValueError:
                raise ValueError(f"bad {letter} value in parser state {body!r}") from None
    modes["coolant"] = " ".join(coolant) or "M9"
    return modes


def number(value: float) -> str:
    """A G-code number with at most four decimals, never written as -0."""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text
