"""Risk levels for every channel and action, decided from what each one is (ADR 0020).

The hub gives every readable channel, writable channel and action one of three levels. Reading is
always low. A write channel or an action gets the highest level any rule below gives it, and when no
rule tells, it gets medium. The rules read only the device file and the device's own description,
so no device name or id appears anywhere in them.

| Rule | Level |
|---|---|
| Reading a channel | low |
| The device file's own `hazard` | at least that level |
| A temperature, length, speed, acceleration, force, torque or pressure unit | high |
| A power above 100 W, a voltage above 50 V or a current above 10 A | high, below that medium |
| An angle, angular speed, volume, flow or mass unit | medium |
| A light unit such as lux or candela | low |
| Words for heat, mains switching, machine motion or force in the name | high |
| Words for pumps, valves, flow, motors, fans and servos in the name | medium |
| Words for light, sound or a display in the name | low |
| No words in the name, the device's own name decides | as its words give |
| A channel mapped to a bare pin, with no words in its name | at least medium |
| Three or more angle or length channels on one device, such as an arm's joints | each of them high |
| A missing unit (dimensionless) or a unit the table doesn't list | one level up |
| An action, from the channels it changes and the units of its arguments | the highest of them |
| Nothing above tells | medium |
| Channels and actions mapped to the same pin | the highest level among them |
| A `risk` override that a person set, with `by` | that level, up or down |
| A `risk` override with no `by` | only ever raises |

Words in a channel's own name can set any level. Words from descriptions and enum values only
raise, so text that came from a device can't lower anything. Low words match whole words only,
while medium and high stems also match inside a word, so a compound such as heatbed counts as heat.

An action can be undone when every effect it lists is a write channel the hub can set back, or
when the safe state runs it. A high action that can't be undone always waits for a person.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from openhal.spec.units import UnitError, convert, normalize_unit, parse_unit, registry

Level = Literal["low", "medium", "high"]
LEVELS: Final[tuple[Level, ...]] = ("low", "medium", "high")
RANK: Final = {"low": 0, "medium": 1, "high": 2}
DEFAULT: Final[Level] = "medium"
PIN_KEY: Final = "pin"
"""The `map` key that names the pin a channel or action drives."""


@dataclass(frozen=True, slots=True)
class Words:
    """One quantity in the word table. `stems` also match inside a longer word."""

    quantity: str
    level: Level
    words: frozenset[str]
    stems: tuple[str, ...] = ()


def _row(quantity: str, level: Level, words: str, stems: str = "") -> Words:
    return Words(quantity, level, frozenset(words.split()), tuple(stems.split()))


WORDS: Final[tuple[Words, ...]] = (
    _row(
        "light",
        "low",
        "light led lamp bulb brightness bright dim dimmer glow backlight color colour rgb rgbw hue saturation "
        "pixel neopixel indicator beacon",
    ),
    _row("sound", "low", "buzzer beep beeper tone volume speaker chime melody pitch sound audio"),
    _row("display", "low", "display screen lcd oled text message label digit segment caption"),
    _row(
        "flow",
        "medium",
        "pump valve flow water watering spray mist dose dosing dispense dispenser sprinkler irrigation drip fluid "
        "liquid feeder",
        "pump valve sprinkl irrigat",
    ),
    _row(
        "motion",
        "medium",
        "motor fan speed servo rotate rotation drive wheel steer steering angle tilt pan door lock latch blind "
        "curtain shade vibration vibrate solenoid",
        "motor servo solenoid",
    ),
    _row(
        "heat",
        "high",
        "heat heater heating heated hot hotend nozzle extruder extrude bed oven kiln furnace boiler stove iron "
        "solder soldering cook cooker grill toaster kettle thermal thermostat temp temperature warm warmer hotplate "
        "peltier fire flame ignite ignition igniter burner torch spark charger charging",
        "heat therm extrud solder furnace flame ignit nozzle hotend",
    ),
    _row(
        "mains",
        "high",
        "relay mains outlet socket plug contactor ssr triac breaker ac",
        "relay mains contactor breaker",
    ),
    _row(
        "machine motion",
        "high",
        "joint axis axes arm shoulder elbow wrist gripper claw spindle laser cnc print printer printing gcode jog "
        "home homing feed feedrate router mill lathe saw blade cutter cut drill crane winch hoist linear actuator "
        "stepper carriage gantry robot move travel goto park x y z",
        "joint spindle laser gripper shoulder elbow wrist gcode stepper actuator robot",
    ),
    _row(
        "force",
        "high",
        "force torque press pressure clamp crush squeeze pneumatic hydraulic compressor vacuum piston",
        "pneumat hydraul compress piston",
    ),
)
"""The quantity each word names. A word in no row says nothing, such as power, level or mode."""


@dataclass(frozen=True, slots=True)
class Dimension:
    """One row of the unit table, by pint dimensionality and how many angles the unit carries."""

    quantity: str
    dimensions: tuple[tuple[str, int], ...]
    angle: int
    level: Level | None
    threshold: tuple[float, str] | None = None
    """For electrical units, above this maximum the unit is high, at or below it medium."""


UNITS: Final[tuple[Dimension, ...]] = (
    Dimension("temperature", (("[temperature]", 1),), 0, "high"),
    Dimension("length", (("[length]", 1),), 0, "high"),
    Dimension("speed", (("[length]", 1), ("[time]", -1)), 0, "high"),
    Dimension("acceleration", (("[length]", 1), ("[time]", -2)), 0, "high"),
    Dimension("force", (("[length]", 1), ("[mass]", 1), ("[time]", -2)), 0, "high"),
    Dimension("torque or energy", (("[length]", 2), ("[mass]", 1), ("[time]", -2)), 0, "high"),
    Dimension("pressure", (("[length]", -1), ("[mass]", 1), ("[time]", -2)), 0, "high"),
    Dimension("power", (("[length]", 2), ("[mass]", 1), ("[time]", -3)), 0, "high", (100.0, "W")),
    Dimension("voltage", (("[current]", -1), ("[length]", 2), ("[mass]", 1), ("[time]", -3)), 0, "high", (50.0, "V")),
    Dimension("current", (("[current]", 1),), 0, "high", (10.0, "A")),
    Dimension("angle", (), 1, "medium"),
    Dimension("angular speed", (("[time]", -1),), 1, "medium"),
    Dimension("volume", (("[length]", 3),), 0, "medium"),
    Dimension("flow", (("[length]", 3), ("[time]", -1)), 0, "medium"),
    Dimension("mass", (("[mass]", 1),), 0, "medium"),
    Dimension("mass flow", (("[mass]", 1), ("[time]", -1)), 0, "medium"),
    Dimension("luminous intensity", (("[luminosity]", 1),), 0, "low"),
    Dimension("luminous flux", (("[luminosity]", 1),), 2, "low"),
    Dimension("illuminance", (("[length]", -2), ("[luminosity]", 1)), 2, "low"),
    Dimension("time", (("[time]", 1),), 0, None),
    Dimension("frequency", (("[time]", -1),), 0, None),
    Dimension("ratio", (), 0, None),
)
"""What each kind of unit says about a write channel or an argument. None means nothing."""

MOTION_UNITS: Final = frozenset({"angle", "length"})
AXES_FOR_MACHINE: Final = 3
DEVICE_WORD_MIN: Final = 3
"""Words from the device's name and model count from three letters, so a model number's X or Z says nothing."""
_SPLIT: Final = re.compile(r"[^a-z]+")
_MIN_STEM_WORD: Final = 4


@dataclass(frozen=True, slots=True)
class Assessment:
    """The level of one target, `read:<name>`, `write:<name>` or `action:<name>`, with the reasons."""

    target: str
    level: Level
    classified: Level
    reasons: tuple[str, ...]
    override: Level | None = None
    override_by: str | None = None
    override_applied: bool = False
    shared_with: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        return self.target.partition(":")[0]

    @property
    def name(self) -> str:
        return self.target.partition(":")[2]

    def view(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "classified": self.classified,
            "reasons": list(self.reasons),
            "override": self.override,
            "override_by": self.override_by,
            "override_applied": self.override_applied,
            "shared_with": list(self.shared_with),
        }


def highest(*levels: Level) -> Level:
    """The highest of the given levels, low when none is given."""
    best: Level = "low"
    for level in levels:
        if RANK[level] > RANK[best]:
            best = level
    return best


def lowest(*levels: Level) -> Level:
    best: Level = "high"
    for level in levels:
        if RANK[level] < RANK[best]:
            best = level
    return best


def up(level: Level) -> Level:
    """One level higher, high staying high."""
    return LEVELS[min(RANK[level] + 1, len(LEVELS) - 1)]


def tokens(*texts: str | None) -> list[str]:
    """Lowercase words from names and text, split at anything that isn't a letter, with plurals as singulars."""
    found: list[str] = []
    for text in texts:
        for word in _SPLIT.split((text or "").lower()):
            if not word:
                continue
            found.append(word)
            if len(word) > _MIN_STEM_WORD and word.endswith("s"):
                found.append(word[:-1])
    return found


def word_levels(words: list[str]) -> list[tuple[Level, str]]:
    """Each quantity the words name, as (level, reason)."""
    found: list[tuple[Level, str]] = []
    for row in WORDS:
        hit = next((word for word in words if word in row.words), None)
        if hit is None and row.level != "low":
            hit = next(
                (word for word in words if len(word) >= _MIN_STEM_WORD and any(stem in word for stem in row.stems)),
                None,
            )
        if hit is not None:
            found.append((row.level, f"{hit} names {row.quantity}"))
    return found


@dataclass(frozen=True, slots=True)
class UnitSignal:
    level: Level | None
    reason: str | None
    odd: bool = False
    motion: bool = False


def _dimension(unit: str) -> Dimension | None:
    parsed = parse_unit(unit)
    dims = tuple(
        sorted((str(key), int(float(str(value)))) for key, value in registry().get_dimensionality(parsed).items())
    )
    _factor, root = registry().get_root_units(parsed)
    angle = int(float(str(dict(root._units).get("radian", 0))))  # noqa: SLF001
    for row in UNITS:
        if row.dimensions == dims and row.angle == angle:
            return row
    return None


def unit_signal(unit: str | None, maximum: float | None) -> UnitSignal:
    """What a write channel's or argument's unit says, given its maximum in that unit."""
    if unit is None:
        return UnitSignal(None, None)
    if normalize_unit(unit) == "dimensionless":
        return UnitSignal(None, "the unit is missing (dimensionless), so one level up", odd=True)
    try:
        row = _dimension(unit)
    except (UnitError, ValueError, TypeError):
        row = None
    if row is None:
        return UnitSignal(None, f"{unit} is a unit the table doesn't list, so one level up", odd=True)
    motion = row.quantity in MOTION_UNITS
    if row.level is None:
        return UnitSignal(None, None)
    if row.threshold is None:
        return UnitSignal(row.level, f"{unit} is {row.quantity}", motion=motion)
    limit, base = row.threshold
    try:
        top = convert(registry().Quantity(maximum, parse_unit(unit)), base) if maximum is not None else math.inf
    except UnitError:
        top = math.inf
    if top > limit:
        return UnitSignal("high", f"{row.quantity} above {limit:g} {base}")
    return UnitSignal("medium", f"{row.quantity} up to {limit:g} {base}")
