import { type ActionSpec, type ArgSpec, type DeviceFile, type Hazard, type WriteChannel, effectiveHazard, hasFileLevelLimits, limitsSha256 } from "./model";
import { formatG } from "./pyformat";
import { convert, dimensions, normalizeUnit, parseUnit } from "./units";

export type Level = Hazard;

export const LEVELS: readonly Level[] = ["low", "medium", "high"];
const RANK: Record<Level, number> = { low: 0, medium: 1, high: 2 };
const DEFAULT: Level = "medium";
/** Provenance sources whose suggested ranges are the device's own or the curated library's. */
export const RANGE_SOURCES: readonly string[] = ["self-described", "driver-describe", "library"];
const PIN_KEY = "pin";

interface Words {
  quantity: string;
  level: Level;
  words: Set<string>;
  stems: string[];
}

function row(quantity: string, level: Level, words: string, stems = ""): Words {
  return { quantity, level, words: new Set(words.split(/\s+/).filter(Boolean)), stems: stems.split(/\s+/).filter(Boolean) };
}

/** The quantity each word names. A word in no row counts for nothing, such as power, level or mode. */
export const WORDS: readonly Words[] = [
  row(
    "light",
    "low",
    "light led lamp bulb brightness bright dim dimmer glow backlight color colour rgb rgbw hue saturation " +
      "pixel neopixel indicator beacon",
  ),
  row("sound", "low", "buzzer beep beeper tone volume speaker chime melody pitch sound audio"),
  row("display", "low", "display screen lcd oled text message label digit segment caption"),
  row(
    "flow",
    "medium",
    "pump valve flow water watering spray mist dose dosing dispense dispenser sprinkler irrigation drip fluid " +
      "liquid feeder",
    "pump valve sprinkl irrigat",
  ),
  row(
    "motion",
    "medium",
    "motor fan speed servo rotate rotation drive wheel steer steering angle tilt pan door lock latch blind " +
      "curtain shade vibration vibrate solenoid",
    "motor servo solenoid",
  ),
  row(
    "heat",
    "high",
    "heat heater heating heated hot hotend nozzle extruder extrude bed oven kiln furnace boiler stove iron " +
      "solder soldering cook cooker grill toaster kettle thermal thermostat temp temperature warm warmer hotplate " +
      "peltier fire flame ignite ignition igniter burner torch spark charger charging",
    "heat therm extrud solder furnace flame ignit nozzle hotend",
  ),
  row("mains", "high", "relay mains outlet socket plug contactor ssr triac breaker ac", "relay mains contactor breaker"),
  row(
    "machine motion",
    "high",
    "joint axis axes arm shoulder elbow wrist gripper claw spindle laser cnc print printer printing gcode jog " +
      "home homing feed feedrate router mill lathe saw blade cutter cut drill crane winch hoist linear actuator " +
      "stepper carriage gantry robot move travel goto park x y z",
    "joint spindle laser gripper shoulder elbow wrist gcode stepper actuator robot",
  ),
  row(
    "force",
    "high",
    "force torque press pressure clamp crush squeeze pneumatic hydraulic compressor vacuum piston",
    "pneumat hydraul compress piston",
  ),
];

interface Dimension {
  quantity: string;
  dims: Array<[string, number]>;
  angle: number;
  level: Level | null;
  /** For electrical units, above this maximum the unit is high, at or below it medium. */
  threshold?: [number, string];
}

function dimension(quantity: string, dims: Record<string, number>, angle: number, level: Level | null, threshold?: [number, string]): Dimension {
  const sorted = Object.keys(dims)
    .sort()
    .map((name): [string, number] => [name, dims[name]]);
  return { quantity, dims: sorted, angle, level, threshold };
}

/** The level each kind of unit gives a write channel or an argument. A null level gives none. */
export const UNITS: readonly Dimension[] = [
  dimension("temperature", { temperature: 1 }, 0, "high"),
  dimension("length", { length: 1 }, 0, "high"),
  dimension("speed", { length: 1, time: -1 }, 0, "high"),
  dimension("acceleration", { length: 1, time: -2 }, 0, "high"),
  dimension("force", { length: 1, mass: 1, time: -2 }, 0, "high"),
  dimension("torque or energy", { length: 2, mass: 1, time: -2 }, 0, "high"),
  dimension("pressure", { length: -1, mass: 1, time: -2 }, 0, "high"),
  dimension("power", { length: 2, mass: 1, time: -3 }, 0, "high", [100, "W"]),
  dimension("voltage", { current: -1, length: 2, mass: 1, time: -3 }, 0, "high", [50, "V"]),
  dimension("current", { current: 1 }, 0, "high", [10, "A"]),
  dimension("angle", {}, 1, "medium"),
  dimension("angular speed", { time: -1 }, 1, "medium"),
  dimension("volume", { length: 3 }, 0, "medium"),
  dimension("flow", { length: 3, time: -1 }, 0, "medium"),
  dimension("mass", { mass: 1 }, 0, "medium"),
  dimension("mass flow", { mass: 1, time: -1 }, 0, "medium"),
  dimension("luminous intensity", { luminosity: 1 }, 0, "low"),
  dimension("luminous flux", { luminosity: 1 }, 2, "low"),
  dimension("illuminance", { length: -2, luminosity: 1 }, 2, "low"),
  dimension("time", { time: 1 }, 0, null),
  dimension("frequency", { time: -1 }, 0, null),
  dimension("ratio", {}, 0, null),
];

const MOTION_UNITS = new Set(["angle", "length"]);
const AXES_FOR_MACHINE = 3;
/** Words from the device's name and model count from three letters, so a model number's X or Z counts for nothing. */
const DEVICE_WORD_MIN = 3;
const SPLIT = /[^a-z]+/;
const MIN_STEM_WORD = 4;

/** The level of one target, `read:<name>`, `write:<name>` or `action:<name>`, with the reasons. */
export interface Assessment {
  target: string;
  level: Level;
  classified: Level;
  reasons: string[];
  override: Level | null;
  overrideBy: string | null;
  overrideApplied: boolean;
  sharedWith: string[];
}

/** The highest of the given levels, low when none is given. */
export function highest(...levels: Level[]): Level {
  return levels.reduce<Level>((top, item) => (RANK[item] > RANK[top] ? item : top), "low");
}

/** The lowest of the given levels, high when none is given. */
export function lowest(...levels: Level[]): Level {
  return levels.reduce<Level>((low, item) => (RANK[item] < RANK[low] ? item : low), "high");
}

/** One level higher, high staying high. */
export function up(level: Level): Level {
  return LEVELS[Math.min(RANK[level] + 1, LEVELS.length - 1)];
}

/** Lowercase words from names and text, split at anything that isn't a letter, with plurals as singulars. */
export function tokens(...texts: Array<string | null | undefined>): string[] {
  const found: string[] = [];
  for (const text of texts) {
    for (const word of (text ?? "").toLowerCase().split(SPLIT)) {
      if (!word) continue;
      found.push(word);
      if (word.length > MIN_STEM_WORD && word.endsWith("s")) found.push(word.slice(0, -1));
    }
  }
  return found;
}

/** Each quantity the words name, as [level, reason]. */
export function wordLevels(words: string[]): Array<[Level, string]> {
  const found: Array<[Level, string]> = [];
  for (const entry of WORDS) {
    let hit = words.find((word) => entry.words.has(word));
    if (hit === undefined && entry.level !== "low") {
      hit = words.find((word) => word.length >= MIN_STEM_WORD && entry.stems.some((stem) => word.includes(stem)));
    }
    if (hit !== undefined) found.push([entry.level, `${hit} names ${entry.quantity}`]);
  }
  return found;
}

interface UnitSignal {
  level: Level | null;
  reason: string | null;
  odd: boolean;
  motion: boolean;
}

const NO_SIGNAL: UnitSignal = { level: null, reason: null, odd: false, motion: false };

function unitRow(unit: string): Dimension | null {
  const { dims, angle } = dimensions(parseUnit(unit));
  const key = JSON.stringify(dims);
  return UNITS.find((item) => JSON.stringify(item.dims) === key && item.angle === angle) ?? null;
}

/** The level a write channel's or argument's unit gives, with the largest magnitude it reaches in that unit. */
export function unitSignal(unit: string | null, maximum: number | null): UnitSignal {
  if (unit === null) return NO_SIGNAL;
  if (normalizeUnit(unit) === "dimensionless") {
    return { level: null, reason: "the unit is missing (dimensionless), so one level up", odd: true, motion: false };
  }
  let found: Dimension | null;
  try {
    found = unitRow(unit);
  } catch {
    found = null;
  }
  if (found === null) return { level: null, reason: `${unit} is a unit the table doesn't list, so one level up`, odd: true, motion: false };
  const motion = MOTION_UNITS.has(found.quantity);
  if (found.level === null) return NO_SIGNAL;
  if (!found.threshold) return { level: found.level, reason: `${unit} is ${found.quantity}`, odd: false, motion };
  const [limit, base] = found.threshold;
  let top = Infinity;
  if (maximum !== null) {
    try {
      top = convert({ magnitude: maximum, unit: parseUnit(unit) }, base);
    } catch {
      top = Infinity;
    }
  }
  if (top > limit) return { level: "high", reason: `${found.quantity} above ${formatG(limit)} ${base}`, odd: false, motion: false };
  return { level: "medium", reason: `${found.quantity} up to ${formatG(limit)} ${base}`, odd: false, motion: false };
}

class Draft {
  constructor(
    public level: Level,
    public reasons: string[] = [],
  ) {}

  raiseTo(level: Level, reason: string): void {
    if (RANK[level] > RANK[this.level]) this.level = level;
    this.reasons.push(reason);
  }
}

function base(nameWords: string[], extraWords: string[], deviceWords: Array<[Level, string]>, units: UnitSignal[], barePin: boolean): Draft {
  const own = wordLevels(nameWords);
  let draft: Draft;
  if (own.length && highest(...own.map(([level]) => level)) === "low" && deviceWords.some(([level]) => level === "high")) {
    draft = new Draft("high", [`${own[0][1]}, but the device name names something high, so high`]);
  } else if (own.length) {
    draft = new Draft(highest(...own.map(([level]) => level)), own.map(([, reason]) => reason));
  } else if (deviceWords.length) {
    draft = new Draft(highest(...deviceWords.map(([level]) => level)), deviceWords.map(([, reason]) => `from the device name, ${reason}`));
  } else {
    draft = new Draft(DEFAULT, ["no rule applies, so medium"]);
  }
  if (barePin && !own.length) draft.raiseTo("medium", "a bare pin, with no word for what is wired to it");
  for (const [level, reason] of wordLevels(extraWords)) {
    if (RANK[level] > RANK.low) draft.raiseTo(level, reason);
  }
  for (const signal of units) {
    if (signal.level !== null && signal.reason !== null) draft.raiseTo(signal.level, signal.reason);
  }
  const odd = units.find((signal) => signal.odd && signal.reason);
  if (odd) {
    draft.level = up(draft.level);
    draft.reasons.push(odd.reason as string);
  }
  return draft;
}

function pinOf(mapping: Record<string, unknown> | null): string | null {
  if (!mapping || !Object.keys(mapping).length || !Object.hasOwn(mapping, PIN_KEY)) return null;
  const value = mapping[PIN_KEY];
  if (typeof value === "bigint") return value.toString();
  if (typeof value === "string") return value;
  return null;
}

/** The largest magnitude a number can take, so a bipolar range counts by its far end. */
function reach(spec: WriteChannel | ArgSpec): number | null {
  const ends = [spec.min, spec.max].filter((value): value is number => value !== null).map(Math.abs);
  return ends.length ? Math.max(...ends) : null;
}

function channelDraft(name: string, spec: WriteChannel, deviceWords: Array<[Level, string]>): [Draft, boolean] {
  const signal = spec.type === "number" ? unitSignal(spec.unit, reach(spec)) : NO_SIGNAL;
  const draft = base(tokens(name), tokens(...spec.values), deviceWords, [signal], pinOf(spec.map) !== null);
  return [draft, signal.motion];
}

function actionDraft(name: string, spec: ActionSpec, deviceWords: Array<[Level, string]>): [Draft, number] {
  const args = Object.values(spec.args);
  const signals = args.filter((arg) => arg.type === "number").map((arg) => unitSignal(arg.unit, reach(arg)));
  const extra = tokens(spec.description, ...Object.keys(spec.args), ...args.flatMap((arg) => arg.values));
  const draft = base(tokens(name), extra, deviceWords, signals, pinOf(spec.map) !== null);
  return [draft, signals.filter((signal) => signal.motion).length];
}

function entries(file: DeviceFile): Array<[string, WriteChannel | ActionSpec]> {
  return [
    ...Object.entries(file.write).map(([name, spec]): [string, WriteChannel | ActionSpec] => [`write:${name}`, spec]),
    ...Object.entries(file.actions).map(([name, spec]): [string, WriteChannel | ActionSpec] => [`action:${name}`, spec]),
  ];
}

function drafts(file: DeviceFile): Map<string, Draft> {
  const named = tokens(file.device.name, file.device.model).filter((word) => word.length >= DEVICE_WORD_MIN);
  const deviceWords = wordLevels(named);
  const found = new Map<string, Draft>();
  const motion: string[] = [];
  for (const [name, channel] of Object.entries(file.write)) {
    const [draft, moves] = channelDraft(name, channel, deviceWords);
    found.set(`write:${name}`, draft);
    if (moves) motion.push(`write:${name}`);
  }
  if (motion.length >= AXES_FOR_MACHINE) {
    for (const item of motion) found.get(item)!.raiseTo("high", `one of ${motion.length} motion axes on this device`);
  }
  for (const [name, action] of Object.entries(file.actions)) {
    const [draft, axes] = actionDraft(name, action, deviceWords);
    if (axes >= AXES_FOR_MACHINE) draft.raiseTo("high", "moves three or more axes at once");
    found.set(`action:${name}`, draft);
  }
  if (file.hazard !== null) {
    for (const draft of found.values()) draft.raiseTo(file.hazard, `the device file's hazard is ${file.hazard}`);
  }
  return found;
}

function sharePins(file: DeviceFile, levels: Map<string, Level>, found: Map<string, Draft>): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  for (const [item, spec] of entries(file)) {
    const pin = pinOf(spec.map);
    if (pin !== null) groups.set(pin, [...(groups.get(pin) ?? []), item]);
  }
  const shared = new Map<string, string[]>();
  for (const members of groups.values()) {
    if (members.length < 2) continue;
    const top = highest(...members.map((member) => levels.get(member)!));
    for (const member of members) {
      const others = members.filter((other) => other !== member);
      shared.set(member, others);
      if (RANK[top] > RANK[levels.get(member)!]) {
        levels.set(member, top);
        found.get(member)!.reasons.push(`shares its pin with ${others.join(", ")}, so ${top}`);
      }
    }
  }
  return shared;
}

function assessAll(file: DeviceFile): Map<string, Assessment> {
  const found = drafts(file);
  const classified = new Map([...found].map(([item, draft]): [string, Level] => [item, draft.level]));
  const levels = new Map(classified);
  const applied = new Set<string>();
  for (const [item, spec] of entries(file)) {
    const override = spec.risk;
    if (override !== null && (RANK[override.level] >= RANK[classified.get(item)!] || override.by !== null)) {
      levels.set(item, override.level);
      applied.add(item);
    }
  }
  for (const [name, action] of Object.entries(file.actions)) {
    const item = `action:${name}`;
    for (const effect of action.effects) {
      const effectLevel = levels.get(`write:${effect}`)!;
      if (RANK[effectLevel] > RANK[levels.get(item)!]) {
        levels.set(item, effectLevel);
        found.get(item)!.reasons.push(`changes ${effect}, which is ${effectLevel}`);
      }
    }
  }
  const shared = sharePins(file, levels, found);
  const result = new Map<string, Assessment>();
  for (const name of Object.keys(file.read)) {
    result.set(`read:${name}`, {
      target: `read:${name}`, level: "low", classified: "low", reasons: ["reading is always low"],
      override: null, overrideBy: null, overrideApplied: false, sharedWith: [],
    });
  }
  for (const [item, spec] of entries(file)) {
    const reasons = [...found.get(item)!.reasons];
    const override = spec.risk;
    if (override !== null) {
      const who = override.by ? `set by ${override.by}` : "in the device file";
      reasons.push(applied.has(item) ? `risk ${override.level} ${who}` : `risk ${override.level} ${who} only raises`);
    }
    result.set(item, {
      target: item,
      level: levels.get(item)!,
      classified: classified.get(item)!,
      reasons,
      override: override?.level ?? null,
      overrideBy: override?.by ?? null,
      overrideApplied: applied.has(item),
      sharedWith: shared.get(item) ?? [],
    });
  }
  return result;
}

const CACHE = new WeakMap<DeviceFile, Map<string, unknown>>();

/** A value computed once per device file. Device files are never changed once loaded, so the value can't go stale. */
function memo<T>(file: DeviceFile, name: string, compute: () => T): T {
  let values = CACHE.get(file);
  if (!values) {
    values = new Map();
    CACHE.set(file, values);
  }
  if (!values.has(name)) values.set(name, compute());
  return values.get(name) as T;
}

/** Every target's level for one file, assessed once per file. */
export function assess(file: DeviceFile): Map<string, Assessment> {
  return memo(file, "assess", () => assessAll(file));
}

/** The level of `read:<name>`, `write:<name>` or `action:<name>`. An unknown target is high. */
export function level(file: DeviceFile, target: string): Level {
  return assess(file).get(target)?.level ?? "high";
}

/** Action words and the word that undoes them, both ways. Start and stop aren't here, since a start can't be undone. */
export const OPPOSITES: Readonly<Record<string, string>> = {
  pause: "resume", open: "close", lock: "unlock", enable: "disable", on: "off",
  extend: "retract", raise: "lower", up: "down", attach: "detach", arm: "disarm",
};
const UNDO = new Map<string, string>([...Object.entries(OPPOSITES), ...Object.entries(OPPOSITES).map(([word, undo]): [string, string] => [undo, word])]);

/** The device's action that undoes `action`, such as resume for pause, if it has one. */
function opposite(file: DeviceFile, action: string): string | null {
  const words = action.split("_");
  for (let index = 0; index < words.length; index++) {
    const undo = UNDO.get(words[index]);
    if (undo === undefined) continue;
    const other = [...words.slice(0, index), undo, ...words.slice(index + 1)].join("_");
    if (Object.hasOwn(file.actions, other)) return other;
  }
  return null;
}

/** True when the hub can undo the action. It lists effects, the safe state runs it, or the device has the action that undoes it. */
export function undoable(file: DeviceFile, action: string): boolean {
  if (file.actions[action].effects.length || file.safe_state.some((step) => step.action === action)) return true;
  return opposite(file, action) !== null;
}

/**
 * The confirmation tier a target uses. `written` is the tier the device file sets. A high hazard
 * device holds every command for a person each time. A high action that can't be undone is held
 * for a person at least once, whatever the file sets.
 */
export function tier(file: DeviceFile, target: string, written: string): string {
  if (effectiveHazard(file) === "high") return "confirm-each-time";
  const [kind, name] = splitTarget(target);
  if (kind === "action" && written === "none" && level(file, target) === "high" && !undoable(file, name)) return "confirm";
  return written;
}

/** Whether a write channel's `max_change_per_s` applies. A low channel ignores a rate that was only suggested. */
export function ownRate(file: DeviceFile, channel: string): boolean {
  return !(file.write[channel].suggested && level(file, `write:${channel}`) === "low");
}

/** The rate limit the kernel applies to a write channel, or null when none applies. */
export function appliedRate(file: DeviceFile, channel: string): number | null {
  return ownRate(file, channel) ? file.write[channel].max_change_per_s : null;
}

/** The level a principal's scope must cover. The device's hazard class, or lower for a lower target. */
export function scopeLevel(file: DeviceFile, target: string): Level {
  return lowest(level(file, target), effectiveHazard(file));
}

function splitTarget(target: string): [string, string] {
  const at = target.indexOf(":");
  return at < 0 ? [target, ""] : [target.slice(0, at), target.slice(at + 1)];
}

/**
 * The write channels and actions that wait for a person's confirmation, as `write.<name>` or
 * `actions.<name>`. Every high risk one, and a low or medium one still marked suggested when the
 * file's ranges came from neither the device itself nor the library.
 */
export function guarded(file: DeviceFile): string[] {
  return memo(file, "guarded", () => {
    const levels = assess(file);
    const source = typeof file.provenance.source === "string" ? file.provenance.source : "hand-written";
    const trusted = RANGE_SOURCES.includes(source);
    const found: string[] = [];
    for (const [kind, label, items] of [
      ["write", "write", file.write],
      ["action", "actions", file.actions],
    ] as const) {
      for (const [name, entry] of Object.entries(items)) {
        if (levels.get(`${kind}:${name}`)!.level === "high" || (entry.suggested && !trusted)) found.push(`${label}.${name}`);
      }
    }
    return found;
  });
}

/** Guarded limits that no person has confirmed yet, or that changed after they were confirmed (ADR 0023). */
export function unconfirmed(file: DeviceFile): string[] {
  return [
    ...memo(file, "unconfirmed", () => {
      const held = guarded(file);
      if (!held.length) return [];
      const bound = file.confirmed?.sha256 ?? null;
      if (bound !== null && bound !== limitsSha256(file)) return ["file (limits changed after they were confirmed)"];
      const missing: string[] = [];
      if (hasFileLevelLimits(file) && file.confirmed === null) missing.push("file (interlocks, watchdog, safe state and hazard)");
      for (const item of held) {
        const [kind, name] = item.split(".", 2);
        const entry = kind === "write" ? file.write[name] : file.actions[name];
        if (entry.suggested || (entry.confirmed === null && file.confirmed === null)) missing.push(item);
      }
      return missing;
    }),
  ];
}

/** What a person must confirm before `write:<name>` or `action:<name>` takes commands, if anything. */
export function readOnly(file: DeviceFile, target: string): string[] {
  const [kind, name] = splitTarget(target);
  const entry = kind === "write" ? `write.${name}` : `actions.${name}`;
  if (!guarded(file).includes(entry)) return [];
  return unconfirmed(file).filter((item) => item === entry || item.startsWith("file "));
}

/** True when every guarded limit is confirmed by a person (spec section 12, ADR 0023). */
export function writable(file: DeviceFile): boolean {
  return unconfirmed(file).length === 0;
}
