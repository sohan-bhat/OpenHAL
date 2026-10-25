import * as expr from "./expressions";
import { formatG, pyFloatRepr, pyStrRepr } from "./pyformat";
import { sha256Hex } from "./sha256";
import { UnitError, convert, parseDuration, parseQuantity, parseRate, parseUnit } from "./units";

export const SPEC_VERSION = "0.1";
export const NAME_PATTERN = /^[a-z][a-z0-9_]{0,47}$/;
export const ID_PATTERN = /^[a-z][a-z0-9-]{0,47}$/;

export const KNOWN_DRIVERS = [
  "serial", "firmata", "openhal-firmware", "scpi", "moonraker", "octoprint", "marlin", "homeassistant", "esphome",
  "rpi-gpio", "rpi-camera", "mqtt", "modbus", "ble", "midi", "hid", "uvc", "http", "grbl", "ros2", "opcua", "sila2",
  "indi", "alpaca", "onvif", "pylabrobot", "lerobot", "mock",
] as const;

const PRIMARY_PARAM: Record<string, string> = {
  serial: "port", firmata: "port", "openhal-firmware": "port", marlin: "port", grbl: "port", scpi: "resource",
  moonraker: "host", octoprint: "host", homeassistant: "host", esphome: "host", http: "base_url", mqtt: "host",
  modbus: "transport", ble: "address", midi: "name", hid: "name", uvc: "name", "rpi-gpio": "pins",
  "rpi-camera": "camera", ros2: "host", opcua: "endpoint", sila2: "host", indi: "host", alpaca: "host",
  onvif: "host", pylabrobot: "backend", lerobot: "robot", mock: "name",
};

export type Hazard = "low" | "medium" | "high";
export type ConfirmTier = "none" | "confirm" | "confirm-each-time";
export type Raw = unknown;

export interface Confirmation {
  by: string;
  at: string;
  sha256: string | null;
}

export interface ValueSpec {
  type: "number" | "bool" | "string" | "enum";
  unit: string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  values: string[];
  max_length: number | null;
  pattern: string | null;
}

export interface WriteChannel extends ValueSpec {
  max_change_per_s: number | null;
  confirm: ConfirmTier;
  confirmed: Confirmation | null;
  suggested: boolean;
  every: number | null;
  map: Record<string, Raw> | null;
}

export type ArgSpec = ValueSpec;

export interface ReadChannel {
  type: "number" | "bool" | "string" | "enum" | "image";
  unit: string | null;
  every: number | null;
  stream: boolean;
  range: [number, number] | null;
  values: string[];
  map: Record<string, Raw> | null;
}

export interface Requirement {
  condition: string;
  message: string | null;
}

export interface MaxRuns {
  count: number;
  per: number;
}

export interface ActionSpec {
  args: Record<string, ArgSpec>;
  require: Array<string | Requirement>;
  max_runs: MaxRuns | null;
  confirm: ConfirmTier;
  confirmed: Confirmation | null;
  suggested: boolean;
  effects: string[];
  description: string | null;
  map: Record<string, Raw> | null;
}

export interface SafeStep {
  values: Record<string, Raw>;
  action: string | null;
  args: Record<string, Raw>;
}

export interface Interlock {
  if_: string;
  require: string;
  message: string | null;
}

export interface MaxDuration {
  when: string;
  for_: number;
  then: "safe_state" | Record<string, Raw>;
  reset_after: number | null;
}

export interface DeviceFile {
  openhal: string;
  device: { name: string; model: string | null; manufacturer: string | null };
  id: string | null;
  match: Record<string, Raw>;
  connect: { driver: string; params: Record<string, Raw> };
  read: Record<string, ReadChannel>;
  write: Record<string, WriteChannel>;
  actions: Record<string, ActionSpec>;
  safe_state: SafeStep[];
  safe_state_note: string | null;
  interlocks: Interlock[];
  watchdog: { heartbeat: number; on_loss: "safe_state" | "hold" | null; max_duration: MaxDuration[] };
  hazard: Hazard | null;
  approvals: Array<Record<string, Raw>>;
  notes: string | null;
  provenance: Record<string, Raw>;
  confirmed: Confirmation | null;
}

export class DeviceFileError extends Error {
  constructor(public problems: string[]) {
    super(problems.join("; "));
  }
}

class Problem extends Error {}

function isMapping(value: Raw): value is Record<string, Raw> {
  return value !== null && typeof value === "object" && !Array.isArray(value) && !(value instanceof Date);
}

function num(value: Raw): number | null {
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "number") return value;
  return null;
}

function str(value: Raw, where: string, max?: number): string {
  if (typeof value !== "string") throw new Problem(`${where}: needs text.`);
  if (max !== undefined && value.length > max) throw new Problem(`${where}: may be at most ${max} characters.`);
  return value;
}

function optStr(value: Raw, where: string, max?: number): string | null {
  return value === undefined || value === null ? null : str(value, where, max);
}

function bool(value: Raw, where: string, fallback = false): boolean {
  if (value === undefined) return fallback;
  if (typeof value !== "boolean") throw new Problem(`${where}: needs true or false.`);
  return value;
}

function oneOf<T extends string>(value: Raw, options: readonly T[], where: string, fallback: T): T {
  if (value === undefined) return fallback;
  if (typeof value !== "string" || !options.includes(value as T)) {
    throw new Problem(`${where}: must be one of ${options.join(", ")}.`);
  }
  return value as T;
}

function strList(value: Raw, where: string): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Problem(`${where}: needs a list of text values.`);
  }
  return value as string[];
}

function seconds(value: Raw, where: string): number {
  try {
    return parseDuration(value);
  } catch (error) {
    throw new Problem(`${where}: ${(error as Error).message}`);
  }
}

function checkUnknownKeys(data: Record<string, Raw>, allowed: string[], where: string): void {
  const extra = Object.keys(data).filter((key) => !allowed.includes(key));
  if (extra.length) throw new Problem(`${where}: unknown ${extra.length > 1 ? "keys" : "key"} ${extra.join(", ")}.`);
}

function confirmation(value: Raw, where: string): Confirmation | null {
  if (value === undefined || value === null) return null;
  if (!isMapping(value)) throw new Problem(`${where}: needs by and at.`);
  checkUnknownKeys(value, ["by", "at", "sha256"], where);
  const by = str(value.by, `${where}.by`, 80);
  if (!by) throw new Problem(`${where}.by: can't be empty.`);
  const at = value.at instanceof Date ? value.at.toISOString().slice(0, 10) : String(value.at ?? "");
  if (!/^\d{4}-\d{2}-\d{2}/.test(at)) throw new Problem(`${where}.at: needs a date such as 2026-10-24.`);
  const sha = value.sha256 === undefined || value.sha256 === null ? null : str(value.sha256, `${where}.sha256`);
  if (sha !== null && !/^[0-9a-f]{64}$/.test(sha)) throw new Problem(`${where}.sha256: needs 64 lowercase hex digits.`);
  return { by, at, sha256: sha };
}

function toUnit(value: Raw, unit: string | null, what: string): Raw {
  if (value === undefined || value === null || unit === null || typeof value === "boolean") return value;
  const number = num(value);
  if (number !== null) return parseQuantity(number, unit).magnitude;
  try {
    return convert(parseQuantity(value, unit), unit);
  } catch (error) {
    if (error instanceof UnitError) throw new Problem(`${what}: ${error.message}`);
    throw error;
  }
}

function limit(value: Raw, where: string): number | null {
  if (value === undefined || value === null) return null;
  const number = num(value);
  if (number === null) throw new Problem(`${where}: needs a number.`);
  return number;
}

const VALUE_KEYS = ["type", "unit", "min", "max", "step", "values", "max_length", "pattern"];

function valueSpec(raw: Raw, where: string, extraKeys: string[]): { spec: ValueSpec; data: Record<string, Raw> } {
  if (!isMapping(raw)) throw new Problem(`${where}: needs a mapping.`);
  checkUnknownKeys(raw, [...VALUE_KEYS, ...extraKeys], where);
  const unit = optStr(raw.unit, `${where}.unit`);
  if (unit !== null) {
    try {
      parseUnit(unit);
    } catch (error) {
      throw new Problem(`${where}: ${(error as Error).message}`);
    }
  }
  const data = { ...raw };
  for (const key of ["min", "max", "step"]) {
    if (key in data) data[key] = toUnit(data[key], unit, `${where}: ${key}`);
  }
  if (data.max_change_per_s !== undefined && data.max_change_per_s !== null && unit !== null) {
    try {
      data.max_change_per_s = parseRate(data.max_change_per_s, unit);
    } catch (error) {
      if (error instanceof UnitError) throw new Problem(`${where}: max_change_per_s: ${error.message}`);
      throw error;
    }
  }
  const type = oneOf(data.type, ["number", "bool", "string", "enum"] as const, `${where}.type`, "number");
  const maxLength = data.max_length === undefined || data.max_length === null ? null : num(data.max_length);
  if (maxLength !== null && (!Number.isInteger(maxLength) || maxLength < 1 || maxLength > 4096)) {
    throw new Problem(`${where}.max_length: must be a whole number from 1 to 4096.`);
  }
  const pattern = optStr(data.pattern, `${where}.pattern`);
  if (pattern !== null) {
    if (pattern.length > 256) throw new Problem(`${where}.pattern: Patterns may be at most 256 characters.`);
    try {
      new RegExp(pattern, "u");
    } catch {
      throw new Problem(`${where}.pattern: Invalid pattern.`);
    }
  }
  const spec: ValueSpec = {
    type,
    unit,
    min: limit(data.min, `${where}.min`),
    max: limit(data.max, `${where}.max`),
    step: limit(data.step, `${where}.step`),
    values: strList(data.values, `${where}.values`),
    max_length: maxLength,
    pattern,
  };
  if (spec.type === "number") {
    if (!spec.unit) throw new Problem(`${where}: Number values need a unit. Use dimensionless for plain counts.`);
    if (spec.min === null || spec.max === null) throw new Problem(`${where}: Number values need both min and max.`);
    if (spec.min > spec.max) throw new Problem(`${where}: min (${formatG(spec.min)}) is above max (${formatG(spec.max)}).`);
    if (spec.step !== null && spec.step <= 0) throw new Problem(`${where}: step must be greater than zero.`);
  } else if (spec.type === "enum") {
    if (!spec.values.length) throw new Problem(`${where}: Enum values need a non-empty values list.`);
    if (new Set(spec.values).size !== spec.values.length) throw new Problem(`${where}: Enum values must be unique.`);
  } else if (spec.type === "string" && spec.max_length === null) {
    throw new Problem(`${where}: String values need max_length.`);
  }
  if (spec.type !== "number" && (spec.min !== null || spec.max !== null || spec.step !== null)) {
    throw new Problem(`${where}: min, max and step only apply to number values.`);
  }
  return { spec, data };
}

function writeChannel(raw: Raw, where: string): WriteChannel {
  const { spec, data } = valueSpec(raw, where, ["max_change_per_s", "confirm", "confirmed", "suggested", "every", "map"]);
  const rate = limit(data.max_change_per_s, `${where}.max_change_per_s`);
  if (rate !== null) {
    if (spec.type !== "number") throw new Problem(`${where}: max_change_per_s only applies to number channels.`);
    if (rate <= 0) throw new Problem(`${where}: max_change_per_s must be greater than zero.`);
  }
  return {
    ...spec,
    max_change_per_s: rate,
    confirm: oneOf(data.confirm, ["none", "confirm", "confirm-each-time"] as const, `${where}.confirm`, "none"),
    confirmed: confirmation(data.confirmed, `${where}.confirmed`),
    suggested: bool(data.suggested, `${where}.suggested`),
    every: data.every === undefined || data.every === null ? null : seconds(data.every, `${where}.every`),
    map: data.map === undefined || data.map === null ? null : (data.map as Record<string, Raw>),
  };
}

function readChannel(raw: Raw, where: string): ReadChannel {
  if (!isMapping(raw)) throw new Problem(`${where}: needs a mapping.`);
  checkUnknownKeys(raw, ["type", "unit", "every", "stream", "range", "values", "map"], where);
  const unit = optStr(raw.unit, `${where}.unit`);
  let range: [number, number] | null = null;
  if (raw.range !== undefined && raw.range !== null) {
    if (!Array.isArray(raw.range) || raw.range.length !== 2) throw new Problem(`${where}.range: needs [low, high].`);
    const items = unit !== null ? raw.range.map((item) => toUnit(item, unit, "range")) : raw.range;
    range = [limit(items[0], `${where}.range`) ?? 0, limit(items[1], `${where}.range`) ?? 0];
  }
  const channel: ReadChannel = {
    type: oneOf(raw.type, ["number", "bool", "string", "enum", "image"] as const, `${where}.type`, "number"),
    unit,
    every: raw.every === undefined || raw.every === null ? null : seconds(raw.every, `${where}.every`),
    stream: bool(raw.stream, `${where}.stream`),
    range,
    values: strList(raw.values, `${where}.values`),
    map: raw.map === undefined || raw.map === null ? null : (raw.map as Record<string, Raw>),
  };
  if (channel.type === "number" && !channel.unit) {
    throw new Problem(`${where}: Number channels need a unit. Use dimensionless for plain counts.`);
  }
  if (channel.every !== null && channel.every < 0.05) throw new Problem(`${where}: every must be at least 50 ms.`);
  if (channel.range !== null && channel.range[0] > channel.range[1]) throw new Problem(`${where}: range must be written low then high.`);
  if (channel.type === "enum" && !channel.values.length) throw new Problem(`${where}: Enum channels need a values list.`);
  return channel;
}

export function conditions(action: ActionSpec): Array<[string, string | null]> {
  return action.require.map((item) => (typeof item === "string" ? [item, null] : [item.condition, item.message]));
}

function requirements(value: Raw, where: string): Array<string | Requirement> {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Problem(`${where}: needs a list.`);
  return value.map((item, index) => {
    if (typeof item === "string") return item;
    const at = `${where}[${index}]`;
    if (!isMapping(item)) throw new Problem(`${at}: needs a condition, or a mapping with condition and message.`);
    checkUnknownKeys(item, ["condition", "message"], at);
    return { condition: str(item.condition, `${at}.condition`, expr.MAX_LENGTH), message: optStr(item.message, `${at}.message`, 300) };
  });
}

function maxRuns(value: Raw, where: string): MaxRuns | null {
  if (value === undefined || value === null) return null;
  if (!isMapping(value)) throw new Problem(`${where}: needs count and per.`);
  checkUnknownKeys(value, ["count", "per"], where);
  const count = num(value.count);
  if (count === null || !Number.isInteger(count) || count < 1 || count > 1000) {
    throw new Problem(`${where}.count: needs a whole number from 1 to 1000.`);
  }
  const per = seconds(value.per, `${where}.per`);
  if (!(per >= 1 && per <= 7 * 86400)) throw new Problem(`${where}: max_runs.per must be between 1 s and 7 days.`);
  return { count, per };
}

function actionSpec(raw: Raw, where: string): ActionSpec {
  if (!isMapping(raw)) throw new Problem(`${where}: needs a mapping.`);
  checkUnknownKeys(raw, ["args", "require", "max_runs", "confirm", "confirmed", "suggested", "effects", "description", "map"], where);
  const args: Record<string, ArgSpec> = {};
  if (raw.args !== undefined) {
    if (!isMapping(raw.args)) throw new Problem(`${where}.args: needs a mapping.`);
    for (const [name, spec] of Object.entries(raw.args)) {
      if (!NAME_PATTERN.test(name)) throw new Problem(`${where}.args: ${pyStrRepr(name)} is not a valid argument name.`);
      args[name] = valueSpec(spec, `${where}.args.${name}`, []).spec;
    }
  }
  return {
    args,
    require: requirements(raw.require, `${where}.require`),
    max_runs: maxRuns(raw.max_runs, `${where}.max_runs`),
    confirm: oneOf(raw.confirm, ["none", "confirm", "confirm-each-time"] as const, `${where}.confirm`, "none"),
    confirmed: confirmation(raw.confirmed, `${where}.confirmed`),
    suggested: bool(raw.suggested, `${where}.suggested`),
    effects: strList(raw.effects, `${where}.effects`),
    description: optStr(raw.description, `${where}.description`, 500),
    map: raw.map === undefined || raw.map === null ? null : (raw.map as Record<string, Raw>),
  };
}

function safeStep(raw: Raw, where: string): SafeStep {
  if (!isMapping(raw)) throw new Problem(`${where}: Each safe state step must be a mapping.`);
  const keys = Object.keys(raw);
  let step: SafeStep;
  if (keys.every((key) => ["values", "action", "args"].includes(key)) && "values" in raw) {
    step =
      raw.action === undefined || raw.action === null
        ? { values: (raw.values as Record<string, Raw>) ?? {}, action: null, args: {} }
        : { values: {}, action: str(raw.action, `${where}.action`), args: (raw.args as Record<string, Raw>) ?? {} };
  } else if ("action" in raw) {
    const extra = keys.filter((key) => key !== "action" && key !== "args").sort();
    if (extra.length) throw new Problem(`${where}: An action step can only have action and args, not ${extra.join(", ")}.`);
    step = { values: {}, action: str(raw.action, `${where}.action`), args: (raw.args as Record<string, Raw>) ?? {} };
  } else {
    step = { values: { ...raw }, action: null, args: {} };
  }
  if (!Object.keys(step.values).length && step.action === null) throw new Problem(`${where}: A safe state step can't be empty.`);
  return step;
}

function connectSpec(raw: Raw): { driver: string; params: Record<string, Raw> } {
  if (!isMapping(raw)) throw new Problem("connect: connect must be a mapping.");
  let driver: string | null = null;
  let params: Record<string, Raw>;
  if ("params" in raw && Object.keys(raw).every((key) => key === "driver" || key === "params")) {
    driver = typeof raw.driver === "string" ? raw.driver : null;
    params = isMapping(raw.params) ? raw.params : {};
  } else {
    const rest = { ...raw };
    driver = typeof rest.driver === "string" ? rest.driver : null;
    delete rest.driver;
    params = rest;
    if (driver === null) {
      for (const key of Object.keys(rest)) {
        if ((KNOWN_DRIVERS as readonly string[]).includes(key)) {
          driver = key;
          const primary = rest[key];
          delete rest[key];
          params = { [PRIMARY_PARAM[key] ?? "target"]: primary, ...rest };
          break;
        }
      }
    }
  }
  if (driver === null) throw new Problem("connect: connect must name a driver, for example driver: serial or serial: auto.");
  if (!(KNOWN_DRIVERS as readonly string[]).includes(driver) && !driver.startsWith("x-")) {
    throw new Problem(`connect.driver: Unknown driver ${pyStrRepr(driver)}. Known drivers are ${[...KNOWN_DRIVERS].sort().join(", ")}.`);
  }
  for (const key of Object.keys(params)) {
    const lower = key.toLowerCase();
    if (["password", "secret", "apikey", "api_key"].some((word) => lower.includes(word)) || lower === "token") {
      throw new Problem(`connect.params: Device files must not hold secrets. Use ${key}_env with an environment variable name.`);
    }
  }
  return { driver, params };
}

const TOP_KEYS = [
  "openhal", "device", "id", "model", "manufacturer", "match", "connect", "read", "write", "actions", "safe_state",
  "safe_state_note", "interlocks", "watchdog", "hazard", "approvals", "notes", "provenance", "confirmed",
];

function channels(file: DeviceFile): Set<string> {
  return new Set([...Object.keys(file.read), ...Object.keys(file.write)]);
}

function enumValues(file: DeviceFile, name: string): string[] {
  if (name in file.write) return file.write[name].values;
  if (name in file.read) return file.read[name].values;
  return [];
}

function checkExpression(file: DeviceFile, text: string, where: string): void {
  let tree: expr.Node;
  try {
    tree = expr.parse(text, channels(file));
  } catch (error) {
    throw new Problem(`${where}: ${(error as Error).message}`);
  }
  const local = new Set([...channels(file)].flatMap((name) => enumValues(file, name)));
  for (const [word, other] of expr.words(tree)) {
    const otherDevice = other !== null && other.kind === "ref" && other.device !== null;
    if (!local.has(word) && !otherDevice) {
      throw new Problem(`${where}: ${pyStrRepr(word)} is not a channel of this device or one of its enum values.`);
    }
    const peers = other !== null && other.kind === "ref" ? enumValues(file, other.name) : [];
    if (other !== null && other.kind === "ref" && other.device === null && peers.length && !peers.includes(word)) {
      throw new Problem(`${where}: ${pyStrRepr(word)} is not one of ${other.name}'s values.`);
    }
  }
  try {
    expr.checkUnits(tree, (ref) => (ref.device === null ? channelUnit(file, ref.name) : null));
  } catch (error) {
    throw new Problem(`${where}: ${(error as Error).message}`);
  }
}

function checkValue(file: DeviceFile, channel: string, value: Raw, where: string): void {
  const spec = file.write[channel];
  if (!spec) throw new Problem(`${where}: ${pyStrRepr(channel)} is not a write channel.`);
  if (spec.type === "number") {
    const magnitude = num(toUnit(value, spec.unit, where));
    if (magnitude === null) throw new Problem(`${where}: ${channel} needs a number.`);
    if (spec.min === null || spec.max === null || !(spec.min <= magnitude && magnitude <= spec.max)) {
      throw new Problem(`${where}: ${typeof value === "number" ? pyFloatRepr(value) : String(value)} is outside ${channel}'s limits.`);
    }
  } else if (spec.type === "bool" && typeof value !== "boolean") {
    throw new Problem(`${where}: ${channel} needs true or false.`);
  } else if (spec.type === "enum" && !spec.values.includes(value as string)) {
    throw new Problem(`${where}: ${pyStrRepr(String(value))} is not one of ${spec.values.join(", ")}.`);
  }
}

function build(data: Record<string, Raw>): DeviceFile {
  const raw: Record<string, Raw> = {};
  for (const [key, value] of Object.entries(data)) if (!key.startsWith("x-")) raw[key] = value;
  checkUnknownKeys(raw, TOP_KEYS, "file");
  let device = raw.device;
  if (typeof device === "string") device = { name: device };
  if (!isMapping(device)) throw new Problem("device: needs a name, or a mapping with name.");
  device = { ...device };
  const identity = device as Record<string, Raw>;
  for (const key of ["model", "manufacturer"]) {
    if (key in raw && !(key in identity)) identity[key] = raw[key];
  }
  checkUnknownKeys(identity, ["name", "model", "manufacturer"], "device");
  const name = str(identity.name, "device.name", 120);
  if (!name) throw new Problem("device.name: can't be empty.");
  const version = raw.openhal === undefined ? SPEC_VERSION : String(raw.openhal);
  if (!/^\d+\.\d+(\.\d+)?$/.test(version)) throw new Problem("openhal: openhal must be a version such as 0.1.");
  if (version.split(".")[0] !== SPEC_VERSION.split(".")[0]) {
    throw new Problem(`openhal: This hub supports spec ${SPEC_VERSION}. The file is version ${version}.`);
  }
  const id = optStr(raw.id, "id");
  if (id !== null && !ID_PATTERN.test(id)) throw new Problem("id: must be a lowercase slug such as desk-fan.");

  const read: Record<string, ReadChannel> = {};
  const write: Record<string, WriteChannel> = {};
  const actions: Record<string, ActionSpec> = {};
  for (const [section, target, make] of [
    ["read", read, readChannel],
    ["write", write, writeChannel],
    ["actions", actions, actionSpec],
  ] as const) {
    const entries = raw[section];
    if (entries === undefined || entries === null) continue;
    if (!isMapping(entries)) throw new Problem(`${section}: needs a mapping of names.`);
    for (const [key, value] of Object.entries(entries)) {
      if (!NAME_PATTERN.test(key)) throw new Problem(`${section}.${key}: names must be lowercase letters, digits and _.`);
      (target as Record<string, unknown>)[key] = (make as (raw: Raw, where: string) => unknown)(value, `${section}.${key}`);
    }
  }

  let safeRaw = raw.safe_state;
  if (isMapping(safeRaw)) safeRaw = [safeRaw];
  if (safeRaw !== undefined && safeRaw !== null && !Array.isArray(safeRaw)) throw new Problem("safe_state: needs a mapping or a list.");
  const safe_state = ((safeRaw as Raw[] | undefined) ?? []).map((step, index) => safeStep(step, `safe_state[${index}]`));

  const interlocks: Interlock[] = [];
  if (raw.interlocks !== undefined && raw.interlocks !== null) {
    if (!Array.isArray(raw.interlocks)) throw new Problem("interlocks: needs a list.");
    raw.interlocks.forEach((item, index) => {
      const where = `interlocks[${index}]`;
      if (!isMapping(item)) throw new Problem(`${where}: needs if and require.`);
      checkUnknownKeys(item, ["if", "require", "message"], where);
      interlocks.push({
        if_: str(item.if, `${where}.if`, expr.MAX_LENGTH),
        require: str(item.require, `${where}.require`, expr.MAX_LENGTH),
        message: optStr(item.message, `${where}.message`, 300),
      });
    });
  }

  const wd = raw.watchdog ?? {};
  if (!isMapping(wd)) throw new Problem("watchdog: needs a mapping.");
  checkUnknownKeys(wd, ["heartbeat", "on_loss", "max_duration"], "watchdog");
  const heartbeat = wd.heartbeat === undefined ? 5 : seconds(wd.heartbeat, "watchdog.heartbeat");
  if (!(heartbeat >= 0.1 && heartbeat <= 3600)) throw new Problem("watchdog.heartbeat: heartbeat must be between 100 ms and 1 h.");
  const maxDuration: MaxDuration[] = [];
  if (wd.max_duration !== undefined && wd.max_duration !== null) {
    if (!Array.isArray(wd.max_duration)) throw new Problem("watchdog.max_duration: needs a list.");
    wd.max_duration.forEach((item, index) => {
      const where = `watchdog.max_duration[${index}]`;
      if (!isMapping(item)) throw new Problem(`${where}: needs when and for.`);
      checkUnknownKeys(item, ["when", "for", "then", "reset_after"], where);
      const then = item.then === undefined ? "safe_state" : item.then;
      if (then !== "safe_state" && !isMapping(then)) throw new Problem(`${where}.then: needs safe_state or channel values.`);
      maxDuration.push({
        when: str(item.when, `${where}.when`, expr.MAX_LENGTH),
        for_: seconds(item.for, `${where}.for`),
        then: then as MaxDuration["then"],
        reset_after: item.reset_after === undefined || item.reset_after === null ? null : seconds(item.reset_after, `${where}.reset_after`),
      });
    });
  }
  const onLoss = wd.on_loss === undefined || wd.on_loss === null ? null : oneOf(wd.on_loss, ["safe_state", "hold"] as const, "watchdog.on_loss", "safe_state");

  const hazard = raw.hazard === undefined || raw.hazard === null ? null : oneOf(raw.hazard, ["low", "medium", "high"] as const, "hazard", "low");
  const file: DeviceFile = {
    openhal: version,
    device: { name, model: optStr(identity.model, "device.model", 120), manufacturer: optStr(identity.manufacturer, "device.manufacturer", 120) },
    id,
    match: isMapping(raw.match) ? raw.match : {},
    connect: connectSpec(raw.connect),
    read,
    write,
    actions,
    safe_state,
    safe_state_note: optStr(raw.safe_state_note, "safe_state_note", 500),
    interlocks,
    watchdog: { heartbeat, on_loss: onLoss, max_duration: maxDuration },
    hazard,
    approvals: Array.isArray(raw.approvals) ? (raw.approvals as Array<Record<string, Raw>>) : [],
    notes: optStr(raw.notes, "notes", 4000),
    provenance: isMapping(raw.provenance) ? raw.provenance : {},
    confirmed: confirmation(raw.confirmed, "confirmed"),
  };

  const names = [...Object.keys(read), ...Object.keys(write), ...Object.keys(actions)];
  const repeated = [...new Set(names.filter((item, index) => names.indexOf(item) !== index))].sort();
  if (repeated.length) throw new Problem(`file: Channel and action names must be unique. Repeated: ${repeated.join(", ")}.`);
  for (const [actionName, action] of Object.entries(actions)) {
    for (const effect of action.effects) {
      if (!(effect in write)) throw new Problem(`actions.${actionName}.effects: ${pyStrRepr(effect)} is not a write channel.`);
    }
    conditions(action).forEach(([condition], index) => checkExpression(file, condition, `actions.${actionName}.require[${index}]`));
  }
  interlocks.forEach((item, index) => {
    checkExpression(file, item.if_, `interlocks[${index}].if`);
    checkExpression(file, item.require, `interlocks[${index}].require`);
  });
  maxDuration.forEach((rule, index) => {
    checkExpression(file, rule.when, `watchdog.max_duration[${index}].when`);
    if (rule.then !== "safe_state") {
      for (const [channel, value] of Object.entries(rule.then)) checkValue(file, channel, value, `watchdog.max_duration[${index}].then`);
    }
  });
  safe_state.forEach((step, index) => {
    if (step.action !== null && !(step.action in actions)) {
      throw new Problem(`safe_state[${index}]: ${pyStrRepr(step.action)} is not an action of this device.`);
    }
    for (const [channel, value] of Object.entries(step.values)) checkValue(file, channel, value, `safe_state[${index}]`);
  });
  return file;
}

export function expandShorthand(data: Raw): Raw {
  if (!isMapping(data)) return data;
  const raw: Record<string, Raw> = {};
  for (const [key, value] of Object.entries(data)) if (!key.startsWith("x-")) raw[key] = value;
  let device = raw.device;
  if (typeof device === "string") device = { name: device };
  if (isMapping(device)) {
    device = { ...device };
    for (const key of ["model", "manufacturer"]) {
      if (key in raw) {
        if (!(key in (device as Record<string, Raw>))) (device as Record<string, Raw>)[key] = raw[key];
        delete raw[key];
      }
    }
    raw.device = device;
  }
  if (isMapping(raw.connect)) {
    const connect = raw.connect;
    if (!("params" in connect && Object.keys(connect).every((key) => key === "driver" || key === "params"))) {
      const rest = { ...connect };
      let driver: Raw = rest.driver;
      delete rest.driver;
      let params: Record<string, Raw> = rest;
      if (driver === undefined) {
        const key = Object.keys(rest).find((name) => (KNOWN_DRIVERS as readonly string[]).includes(name));
        if (key) {
          driver = key;
          const primary = rest[key];
          delete rest[key];
          params = { [PRIMARY_PARAM[key] ?? "target"]: primary, ...rest };
        }
      }
      raw.connect = driver === undefined ? { params } : { driver, params };
    }
  }
  let safe = raw.safe_state;
  if (isMapping(safe)) safe = [safe];
  if (Array.isArray(safe)) {
    raw.safe_state = safe.map((step) => {
      if (!isMapping(step)) return step;
      const keys = Object.keys(step);
      if (keys.every((key) => ["values", "action", "args"].includes(key)) && "values" in step) {
        return step.action === undefined || step.action === null ? { values: step.values } : { action: step.action, args: step.args ?? {} };
      }
      if ("action" in step) return step;
      return { values: { ...step } };
    });
  }
  return raw;
}

export function loadDeviceFile(data: Raw): DeviceFile {
  if (!isMapping(data)) throw new DeviceFileError(["file: A device file must be a mapping at the top level."]);
  try {
    return build(data);
  } catch (error) {
    if (error instanceof Problem) throw new DeviceFileError([error.message]);
    throw error;
  }
}

export function deviceId(file: DeviceFile): string {
  if (file.id) return file.id;
  let slug = file.device.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!slug || !/^[a-z]/.test(slug)) slug = `device-${slug}`.replace(/^-+|-+$/g, "");
  return slug.slice(0, 48).replace(/-+$/, "");
}

export function effectiveHazard(file: DeviceFile): Hazard {
  if (file.hazard !== null) return file.hazard;
  return Object.keys(file.write).length || Object.keys(file.actions).length ? "medium" : "low";
}

export function channelUnit(file: DeviceFile, name: string): string | null {
  if (name in file.write) return file.write[name].unit;
  if (name in file.read) return file.read[name].unit;
  return null;
}

export function channelNames(file: DeviceFile): Set<string> {
  return channels(file);
}

function hasFileLevelLimits(file: DeviceFile): boolean {
  return Boolean(file.interlocks.length || file.watchdog.max_duration.length || file.safe_state.length || file.hazard !== null);
}

export function unconfirmed(file: DeviceFile): string[] {
  const bound = file.confirmed?.sha256 ?? null;
  if (bound !== null && bound !== limitsSha256(file)) return ["file (limits changed after they were confirmed)"];
  const missing: string[] = [];
  const writes = Object.keys(file.write).length > 0 || Object.keys(file.actions).length > 0;
  if (writes && hasFileLevelLimits(file) && file.confirmed === null) missing.push("file (interlocks, watchdog, safe state and hazard)");
  for (const [kind, entries] of [
    ["write", file.write],
    ["actions", file.actions],
  ] as const) {
    for (const [name, entry] of Object.entries(entries)) {
      if (entry.suggested || (entry.confirmed === null && file.confirmed === null)) missing.push(`${kind}.${name}`);
    }
  }
  return missing;
}

export function writable(file: DeviceFile): boolean {
  return unconfirmed(file).length === 0;
}


class PyFloat {
  constructor(public value: number) {}
}

function f(value: number | null): PyFloat | null {
  return value === null ? null : new PyFloat(value);
}

function secondsText(value: number | null): string | null {
  return value === null ? null : `${formatG(value)} s`;
}

function dumpValueSpec(spec: ValueSpec): Record<string, unknown> {
  return {
    type: spec.type,
    unit: spec.unit,
    min: f(spec.min),
    max: f(spec.max),
    step: f(spec.step),
    values: spec.values,
    max_length: spec.max_length === null ? null : BigInt(spec.max_length),
    pattern: spec.pattern,
  };
}

function limitsData(file: DeviceFile): Record<string, unknown> {
  const mapOrNull = (value: Record<string, Raw> | null) => value;
  return {
    openhal: file.openhal,
    device: file.device,
    id: file.id,
    match: {
      usb: [], usb_class: null, serial_number: null, scpi_idn: null, ble_services: [], ble_name: null, mdns: null,
      modbus_id: null, homeassistant: null, moonraker: {}, esphome: {}, firmware: {},
      ...file.match,
    },
    connect: file.connect,
    read: Object.fromEntries(
      Object.entries(file.read).map(([name, ch]) => [
        name,
        {
          type: ch.type, unit: ch.unit, every: secondsText(ch.every), stream: ch.stream,
          range: ch.range === null ? null : ch.range.map((item) => new PyFloat(item)), values: ch.values, map: mapOrNull(ch.map),
        },
      ]),
    ),
    write: Object.fromEntries(
      Object.entries(file.write).map(([name, ch]) => [
        name,
        {
          ...dumpValueSpec(ch), max_change_per_s: f(ch.max_change_per_s), confirm: ch.confirm, suggested: ch.suggested,
          every: secondsText(ch.every), map: mapOrNull(ch.map),
        },
      ]),
    ),
    actions: Object.fromEntries(
      Object.entries(file.actions).map(([name, action]) => [
        name,
        {
          args: Object.fromEntries(Object.entries(action.args).map(([arg, spec]) => [arg, dumpValueSpec(spec)])),
          require: action.require,
          max_runs: action.max_runs === null ? null : { count: action.max_runs.count, per: secondsText(action.max_runs.per) },
          confirm: action.confirm, suggested: action.suggested, effects: action.effects,
          description: action.description, map: mapOrNull(action.map),
        },
      ]),
    ),
    safe_state: file.safe_state.map((step) => {
      if (step.action !== null) return Object.keys(step.args).length ? { action: step.action, args: step.args } : { action: step.action };
      return step.values;
    }),
    interlocks: file.interlocks.map((item) => ({ if: item.if_, require: item.require, message: item.message })),
    watchdog: {
      heartbeat: secondsText(file.watchdog.heartbeat),
      on_loss: file.watchdog.on_loss,
      max_duration: file.watchdog.max_duration.map((rule) => ({
        when: rule.when, for: secondsText(rule.for_), then: rule.then, reset_after: secondsText(rule.reset_after),
      })),
    },
    hazard: file.hazard,
  };
}

function jsonString(text: string): string {
  let out = '"';
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const code = text.charCodeAt(i);
    if (char === '"') out += '\\"';
    else if (char === "\\") out += "\\\\";
    else if (char === "\n") out += "\\n";
    else if (char === "\r") out += "\\r";
    else if (char === "\t") out += "\\t";
    else if (char === "\b") out += "\\b";
    else if (char === "\f") out += "\\f";
    else if (code < 0x20 || code > 0x7e) out += `\\u${code.toString(16).padStart(4, "0")}`;
    else out += char;
  }
  return `${out}"`;
}

export function pyJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (value instanceof PyFloat) return pyFloatRepr(value.value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "bigint") return value.toString();
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : pyFloatRepr(value);
  if (typeof value === "string") return jsonString(value);
  if (value instanceof Date) return jsonString(value.toISOString().slice(0, 10));
  if (Array.isArray(value)) return `[${value.map(pyJson).join(",")}]`;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys.map((key) => `${jsonString(key)}:${pyJson(record[key])}`).join(",")}}`;
}

export function limitsSha256(file: DeviceFile): string {
  return sha256Hex(pyJson(limitsData(file)));
}
