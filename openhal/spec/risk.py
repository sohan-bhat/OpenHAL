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
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from openhal.spec.units import UnitError, convert, normalize_unit, parse_unit, registry

if TYPE_CHECKING:
    from openhal.spec.models import Action, ArgSpec, DeviceFile, WriteChannel

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


@dataclass
class _Draft:
    level: Level
    reasons: list[str] = field(default_factory=list)

    def raise_to(self, level: Level, reason: str) -> None:
        if RANK[level] > RANK[self.level]:
            self.level = level
        self.reasons.append(reason)


def _base(
    name_words: list[str],
    extra_words: list[str],
    device_words: list[tuple[Level, str]],
    units: list[UnitSignal],
    *,
    bare_pin: bool,
) -> _Draft:
    """The level from words and units, before the device-wide rules."""
    own = word_levels(name_words)
    if own:
        draft = _Draft(highest(*(level for level, _ in own)), [reason for _, reason in own])
    elif device_words:
        draft = _Draft(
            highest(*(level for level, _ in device_words)), [f"the device name says {r}" for _, r in device_words]
        )
    else:
        draft = _Draft(DEFAULT, ["nothing in the name tells, so medium"])
    if bare_pin and not own:
        draft.raise_to("medium", "a bare pin, and the hub can't know what is wired to it")
    for level, reason in word_levels(extra_words):
        if RANK[level] > RANK["low"]:
            draft.raise_to(level, reason)
    for signal in units:
        if signal.level is not None and signal.reason is not None:
            draft.raise_to(signal.level, signal.reason)
    if any(signal.odd for signal in units):
        odd = next(signal.reason for signal in units if signal.odd and signal.reason)
        draft.level = up(draft.level)
        draft.reasons.append(odd)
    return draft


def _pin(mapping: dict[str, Any] | None) -> str | None:
    if not mapping or PIN_KEY not in mapping:
        return None
    value = mapping[PIN_KEY]
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    return str(value)


def _channel_draft(name: str, spec: WriteChannel, device_words: list[tuple[Level, str]]) -> tuple[_Draft, bool]:
    signal = unit_signal(spec.unit, spec.max) if spec.type == "number" else UnitSignal(None, None)
    draft = _base(
        tokens(name),
        tokens(*spec.values),
        device_words,
        [signal],
        bare_pin=_pin(spec.map) is not None,
    )
    return draft, signal.motion


def _action_draft(name: str, spec: Action, device_words: list[tuple[Level, str]]) -> _Draft:
    signals = [unit_signal(arg.unit, arg.max) for arg in spec.args.values() if arg.type == "number"]
    extra = tokens(spec.description, *spec.args, *(value for arg in spec.args.values() for value in arg.values))
    return _base(tokens(name), extra, device_words, signals, bare_pin=_pin(spec.map) is not None)


def _arg_motion(args: dict[str, ArgSpec]) -> int:
    return sum(1 for arg in args.values() if arg.type == "number" and unit_signal(arg.unit, arg.max).motion)


def _entries(file: DeviceFile) -> list[tuple[str, WriteChannel | Action]]:
    """Every write channel and action as (target, spec)."""
    found: list[tuple[str, WriteChannel | Action]] = [(f"write:{name}", spec) for name, spec in file.write.items()]
    return found + [(f"action:{name}", spec) for name, spec in file.actions.items()]


def _drafts(file: DeviceFile) -> dict[str, _Draft]:
    """Each target's level from its words and units, the axis rule and the hazard floor."""
    named = [word for word in tokens(file.device.name, file.device.model) if len(word) >= DEVICE_WORD_MIN]
    device_words = word_levels(named)
    drafts: dict[str, _Draft] = {}
    motion: list[str] = []
    for name, channel in file.write.items():
        drafts[f"write:{name}"], moves = _channel_draft(name, channel, device_words)
        if moves:
            motion.append(f"write:{name}")
    if len(motion) >= AXES_FOR_MACHINE:
        for target in motion:
            drafts[target].raise_to("high", f"one of {len(motion)} motion axes on this device")
    for name, action in file.actions.items():
        draft = _action_draft(name, action, device_words)
        if _arg_motion(action.args) >= AXES_FOR_MACHINE:
            draft.raise_to("high", "moves three or more axes at once")
        drafts[f"action:{name}"] = draft
    if file.hazard is not None:
        for draft in drafts.values():
            draft.raise_to(file.hazard, f"the device file's hazard is {file.hazard}")
    return drafts


def _share_pins(file: DeviceFile, levels: dict[str, Level], drafts: dict[str, _Draft]) -> dict[str, tuple[str, ...]]:
    """Give every target on one pin the highest level among them. Returns who shares with whom."""
    groups: dict[str, list[str]] = {}
    for target, spec in _entries(file):
        pin = _pin(spec.map)
        if pin is not None:
            groups.setdefault(pin, []).append(target)
    shared: dict[str, tuple[str, ...]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        top = highest(*(levels[member] for member in members))
        for member in members:
            others = tuple(other for other in members if other != member)
            shared[member] = others
            if RANK[top] > RANK[levels[member]]:
                levels[member] = top
                drafts[member].reasons.append(f"shares its pin with {', '.join(others)}, so {top}")
    return shared


def _assess(file: DeviceFile) -> dict[str, Assessment]:
    drafts = _drafts(file)
    classified = {target: draft.level for target, draft in drafts.items()}
    levels = dict(classified)
    applied: set[str] = set()
    for target, spec in _entries(file):
        if spec.risk is not None and (RANK[spec.risk.level] >= RANK[classified[target]] or spec.risk.by is not None):
            levels[target] = spec.risk.level
            applied.add(target)
    for name, action in file.actions.items():
        target = f"action:{name}"
        for effect in action.effects:
            effect_level = levels[f"write:{effect}"]
            if RANK[effect_level] > RANK[levels[target]]:
                levels[target] = effect_level
                drafts[target].reasons.append(f"changes {effect}, which is {effect_level}")
    shared = _share_pins(file, levels, drafts)
    result: dict[str, Assessment] = {
        f"read:{name}": Assessment(f"read:{name}", "low", "low", ("reading is always low",)) for name in file.read
    }
    for target, spec in _entries(file):
        reasons = list(drafts[target].reasons)
        override = spec.risk
        if override is not None:
            who = f"set by {override.by}" if override.by else "in the device file"
            counts = target in applied
            reasons.append(f"risk {override.level} {who}" if counts else f"risk {override.level} {who} only raises")
        result[target] = Assessment(
            target,
            levels[target],
            classified[target],
            tuple(reasons),
            override=override.level if override is not None else None,
            override_by=override.by if override is not None else None,
            override_applied=target in applied,
            shared_with=shared.get(target, ()),
        )
    return result


_CACHE: dict[int, tuple[weakref.ref[DeviceFile], dict[str, Any]]] = {}


def memo[T](file: DeviceFile, name: str, compute: Callable[[], T]) -> T:
    """A value computed once per device file. Device files are frozen, so the value can't go stale."""
    key = id(file)
    hit = _CACHE.get(key)
    if hit is None or hit[0]() is not file:

        def forget(_ref: weakref.ref[DeviceFile], key: int = key) -> None:
            _CACHE.pop(key, None)

        hit = (weakref.ref(file, forget), {})
        _CACHE[key] = hit
    values = hit[1]
    if name not in values:
        values[name] = compute()
    found: T = values[name]
    return found


def assess(file: DeviceFile) -> dict[str, Assessment]:
    """Every target's level for one file, assessed once per file."""
    return memo(file, "assess", lambda: _assess(file))


def level(file: DeviceFile, target: str) -> Level:
    """The level of `read:<name>`, `write:<name>` or `action:<name>`. An unknown target is high."""
    found = assess(file).get(target)
    return found.level if found is not None else "high"


def undoable(file: DeviceFile, action: str) -> bool:
    """True when the hub can undo the action, because its effects are write channels or the safe state runs it."""
    spec = file.actions[action]
    if any(step.action == action for step in file.safe_state):
        return True
    return bool(spec.effects) and all(effect in file.write for effect in spec.effects)


def tier(file: DeviceFile, target: str, written: str) -> str:
    """The confirmation tier a target uses. `written` is the tier the device file sets.

    A high hazard device holds every command for a person each time. A high action that can't be
    undone waits for a person at least once, whatever the file sets.
    """
    if file.effective_hazard == "high":
        return "confirm-each-time"
    kind, _, name = target.partition(":")
    if kind == "action" and written == "none" and level(file, target) == "high" and not undoable(file, name):
        return "confirm"
    return written


def own_rate(file: DeviceFile, channel: str) -> bool:
    """Whether a write channel's `max_change_per_s` applies. A low channel ignores a rate that was only suggested."""
    spec = file.write[channel]
    return not (spec.suggested and level(file, f"write:{channel}") == "low")


def scope_level(file: DeviceFile, target: str) -> Level:
    """The level a principal's scope must cover. The device's hazard class, or lower for a lower target."""
    return lowest(level(file, target), file.effective_hazard)
