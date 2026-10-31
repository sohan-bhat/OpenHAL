import type { Decision, DeviceFile } from "./kernel";
import { formatG } from "./kernel/pyformat";
import { UnitError, convert, parseQuantity } from "./kernel/units";

export type Data = Record<string, unknown>;
type Template = (data: Data) => string;

export interface RegistryEntry {
  code: number;
  name: string;
  kernelCodes: string[];
  meaning: string;
  template: Template;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data: Data;
}

const has = (data: Data, key: string): boolean => {
  const value = data[key];
  if (value === undefined || value === null || value === "" || value === false || value === 0) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
};

export interface Quantity {
  value: number;
  unit: string;
}

function isQuantity(value: unknown): value is Quantity {
  return value !== null && typeof value === "object" && "value" in value && !!(value as Quantity).unit;
}

export function shown(value: unknown): string {
  if (isQuantity(value)) return `${formatG(Number(value.value), 6)} ${value.unit === "percent" ? "%" : value.unit}`;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value);
  return String(value);
}

function pyJsonText(value: unknown): string {
  if (typeof value === "string") {
    let out = '"';
    for (const char of value) {
      const code = char.codePointAt(0)!;
      if (char === '"') out += '\\"';
      else if (char === "\\") out += "\\\\";
      else if (char === "\n") out += "\\n";
      else if (char === "\t") out += "\\t";
      else if (code < 0x20 || code > 0x7e) {
        const units = code > 0xffff ? [0xd800 + ((code - 0x10000) >> 10), 0xdc00 + ((code - 0x10000) & 0x3ff)] : [code];
        out += units.map((unit) => `\\u${unit.toString(16).padStart(4, "0")}`).join("");
      } else out += char;
    }
    return `${out}"`;
  }
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value === null || value === undefined) return "null";
  if (Array.isArray(value)) return `[${value.map(pyJsonText).join(", ")}]`;
  return `{${Object.entries(value as Record<string, unknown>).map(([key, item]) => `${pyJsonText(key)}: ${pyJsonText(item)}`).join(", ")}}`;
}

function requestedShown(data: Data): string | null {
  return data.requested !== undefined && data.requested !== null ? shown(data.requested) : null;
}

function subject(data: Data): string {
  if (has(data, "channel")) return [String(data.channel), requestedShown(data)].filter((part): part is string => part !== null).join(" ");
  if (has(data, "action") && has(data, "argument")) {
    return [String(data.action), String(data.argument), requestedShown(data)].filter((part): part is string => !!part).join(" ");
  }
  if (has(data, "action")) return has(data, "device") ? `${data.action} on ${data.device}` : String(data.action);
  return has(data, "device") ? String(data.device) : "The command";
}

function provenance(data: Data): string {
  const parts: string[] = [];
  if (has(data, "file")) parts.push(String(data.file));
  if (has(data, "confirmedBy")) parts.push(`confirmed by ${data.confirmedBy}${has(data, "confirmedAt") ? ` ${data.confirmedAt}` : ""}`);
  return parts.length ? ` (${parts.join(", ")})` : "";
}

const session = (data: Data): string => ` (tightened by ${data.tightenedBy})`;

function limitExceeded(data: Data): string {
  if (!has(data, "limit")) return `${subject(data)} is outside its confirmed limits${provenance(data)}`;
  const tightened = has(data, "tightenedBy");
  const verb = data.kernelCode === "below_min" ? "is below" : "exceeds";
  const text = `${subject(data)} ${verb} the ${tightened ? "session limit" : "limit"} of ${shown(data.limit)}`;
  return text + (tightened ? session(data) : provenance(data));
}

function rateLimited(data: Data): string {
  if (has(data, "runs") && has(data, "per")) {
    return `${has(data, "action") ? data.action : "The action"} may run at most ${data.runs} times per ${shown(data.per)}${provenance(data)}`;
  }
  if (!has(data, "limit")) return `${subject(data)} changes faster than allowed right now${provenance(data)}`;
  const limit = shown(data.limit);
  if (has(data, "tightenedBy")) return `${subject(data)} changes faster than the session limit of ${limit} allows right now${session(data)}`;
  return `${subject(data)} changes faster than ${limit} allows right now${provenance(data)}`;
}

function unitInvalid(data: Data): string {
  if (has(data, "expected")) {
    const name = has(data, "argument") ? data.argument : has(data, "channel") ? data.channel : "The value";
    const sent = typeof data.requested === "string" ? `, not ${pyJsonText(data.requested)}` : "";
    return `${name} needs its number and unit apart, as ${pyJsonText(data.expected)}${sent}`;
  }
  return `${subject(data)} needs a finite number with a unit it can convert${provenance(data)}`;
}

function invalidValue(data: Data): string {
  if (data.kernelCode === "bad_step" && has(data, "limit")) return `${subject(data)} is not a step of ${shown(data.limit)}${provenance(data)}`;
  return `${subject(data)} is not a value it accepts${provenance(data)}`;
}

function unknownTarget(data: Data): string {
  if (has(data, "device") && has(data, "channel")) return `${data.device} has no channel ${data.channel}`;
  if (has(data, "device") && has(data, "action")) return `${data.device} has no action ${data.action}`;
  if (has(data, "device")) return `There is no device ${data.device}`;
  if (has(data, "requestId")) return `There is no request ${data.requestId}`;
  if (has(data, "routine")) return `There is no routine ${data.routine}`;
  return "There is no such device, channel, action or routine";
}

function invalidParams(data: Data): string {
  const problems = Array.isArray(data.problems) ? data.problems : [];
  return problems.length ? `The params don't match the method's schema. ${problems[0]}` : "The params don't match the method's schema";
}

const device = (data: Data, fallback: string): string => (has(data, "device") ? String(data.device) : fallback);
const fixed = (text: string): Template => () => text;

export const ERROR_REGISTRY: RegistryEntry[] = [
  { code: -32700, name: "PARSE_ERROR", kernelCodes: [], meaning: "Invalid JSON", template: fixed("The message is not valid JSON") },
  { code: -32600, name: "INVALID_REQUEST", kernelCodes: [], meaning: "Not a JSON-RPC request", template: fixed("The message is not a JSON-RPC 2.0 request") },
  {
    code: -32601,
    name: "METHOD_NOT_FOUND",
    kernelCodes: [],
    meaning: "Unknown method, or one above the hub's conformance level",
    template: (data) => (has(data, "method") ? `This hub has no method ${data.method} at its conformance level` : "This hub has no such method"),
  },
  { code: -32602, name: "INVALID_PARAMS", kernelCodes: ["bad_request"], meaning: "Params don't match the schema", template: invalidParams },
  {
    code: -32603,
    name: "INTERNAL_ERROR",
    kernelCodes: ["internal_error"],
    meaning: "A bug in the hub",
    template: fixed("The hub hit an unexpected error and nothing was sent to the device"),
  },
  { code: -32001, name: "NOT_INITIALIZED", kernelCodes: [], meaning: "hal/initialize hasn't run", template: fixed("Send hal/initialize first") },
  {
    code: -32002,
    name: "UNAUTHORIZED",
    kernelCodes: [],
    meaning: "Missing or unknown token",
    template: fixed("A valid token is required. Create one with openhal token create"),
  },
  {
    code: -32003,
    name: "SCOPE_DENIED",
    kernelCodes: ["not_permitted"],
    meaning: "The principal's token scope doesn't cover this device or method",
    template: (data) =>
      has(data, "device")
        ? `This token's scope doesn't cover ${data.device}`
        : has(data, "method")
          ? `Calling ${data.method} takes a human principal`
          : "This token's scope doesn't cover this method",
  },
  { code: -32004, name: "UNKNOWN_TARGET", kernelCodes: ["unknown_target"], meaning: "No such device, channel or action", template: unknownTarget },
  {
    code: -32005,
    name: "DEVICE_UNAVAILABLE",
    kernelCodes: ["device_unavailable"],
    meaning: "Disconnected or not ready",
    template: (data) => `${device(data, "The device")} is disconnected or not ready`,
  },
  { code: -32010, name: "LIMIT_EXCEEDED", kernelCodes: ["above_max", "below_min"], meaning: "Outside the device file's confirmed limits", template: limitExceeded },
  { code: -32011, name: "RATE_LIMITED", kernelCodes: ["rate_limited"], meaning: "Faster than max_change_per_s allows right now", template: rateLimited },
  {
    code: -32012,
    name: "INTERLOCK_BLOCKED",
    kernelCodes: ["interlock"],
    meaning: "An interlock or action requirement doesn't hold, or a value it needs is unknown",
    template: (data) =>
      has(data, "interlock") ? String(data.interlock) : `${subject(data)} is held back by an interlock or requirement that doesn't hold${provenance(data)}`,
  },
  {
    code: -32013,
    name: "CONFIRMATION_REQUIRED",
    kernelCodes: ["needs_confirmation"],
    meaning: "Queued for a person, data.requestId names the request",
    template: (data) =>
      has(data, "requestId") ? `${subject(data)} is held until a person approves request ${data.requestId}` : `${subject(data)} needs a person to approve it`,
  },
  { code: -32014, name: "STOPPED", kernelCodes: ["stopped"], meaning: "The hub is stopped until a person unlocks", template: fixed("The hub is stopped until a person unlocks it") },
  {
    code: -32015,
    name: "UNVERIFIED_LIMITS",
    kernelCodes: ["read_only_file"],
    meaning: "The device file's limits aren't confirmed by a person, so it is read-only",
    template: (data) => `${device(data, "The device")} is read-only until a person confirms its limits${provenance(data)}`,
  },
  { code: -32016, name: "INVALID_VALUE", kernelCodes: ["bad_value", "bad_step"], meaning: "Wrong type, step, enum value or pattern", template: invalidValue },
  {
    code: -32017,
    name: "WATCHDOG_TRIPPED",
    kernelCodes: ["duration_exceeded"],
    meaning: "A watchdog budget is used up",
    template: (data) => `A watchdog budget on ${device(data, "the device")} is used up until it resets${provenance(data)}`,
  },
  {
    code: -32018,
    name: "BUSY",
    kernelCodes: ["busy"],
    meaning: "Another command holds the device",
    template: (data) => `${device(data, "The device")} is busy with another command. Try again`,
  },
  {
    code: -32019,
    name: "QUEUE_FULL",
    kernelCodes: ["queue_full"],
    meaning: "The confirmation queue is full",
    template: fixed("The confirmation queue is full. Wait for pending requests to be decided"),
  },
  {
    code: -32020,
    name: "DRIVER_ERROR",
    kernelCodes: ["driver_error"],
    meaning: "The device or its protocol failed, and the channel is unknown until a readback",
    template: (data) =>
      `${device(data, "The device")} didn't complete the command, so ${has(data, "channel") ? data.channel : "what it touched"} is unknown until a readback`,
  },
  {
    code: -32021,
    name: "MISCONFIGURED",
    kernelCodes: ["misconfigured", "cannot_loosen"],
    meaning: "The hub's device files are inconsistent, or a change would loosen a confirmed limit",
    template: (data) =>
      data.kernelCode === "cannot_loosen"
        ? `${subject(data)} can only be tightened, never loosened`
        : "The hub's device files are inconsistent, so nothing can be written until they are fixed",
  },
  {
    code: -32022,
    name: "REQUEST_CLOSED",
    kernelCodes: ["expired", "rejected"],
    meaning: "The confirmation request expired or was rejected",
    template: (data) => (has(data, "requestId") ? `Request ${data.requestId} is closed` : "The request is closed"),
  },
  {
    code: -32023,
    name: "UNIT_INVALID",
    kernelCodes: ["bad_unit"],
    meaning: "A missing, unknown or incompatible unit, or a value that isn't finite",
    template: unitInvalid,
  },
];

export function registryByName(name: string): RegistryEntry {
  const entry = ERROR_REGISTRY.find((item) => item.name === name);
  if (!entry) throw new Error(`No registry entry named ${name}.`);
  return entry;
}

export function registryFor(kernelCode: string | null): RegistryEntry {
  return ERROR_REGISTRY.find((item) => kernelCode !== null && item.kernelCodes.includes(kernelCode)) ?? registryByName("INTERNAL_ERROR");
}

export function rpcError(name: string, data: Data = {}, message?: string): JsonRpcError {
  const entry = registryByName(name);
  const kept: Data = { name: entry.name };
  for (const [key, value] of Object.entries(data)) if (value !== undefined && value !== null && key !== "name") kept[key] = value;
  return { code: entry.code, message: message ?? entry.template(kept), data: kept };
}

export function fromKernel(kernelCode: string | null, data: Data = {}): JsonRpcError {
  return rpcError(registryFor(kernelCode).name, { kernelCode, ...data });
}

export const PROVENANCE_NAMES = new Set(["LIMIT_EXCEEDED", "RATE_LIMITED", "INVALID_VALUE", "UNIT_INVALID", "INTERLOCK_BLOCKED", "WATCHDOG_TRIPPED"]);

const LIMIT_KEYS: Record<string, string> = { above_max: "max", below_min: "min", bad_step: "step", rate_limited: "rate_per_s" };

export interface Facts {
  file: string | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  unit: string | null;
  number: boolean;
  limits: Record<string, number>;
}

export function targetParts(target: string | null): [string | null, string | null] {
  const [kind, ...rest] = (target ?? "").split(":");
  const name = rest.join(":") || null;
  if (kind === "write" || kind === "read") return [name, null];
  if (kind === "action") return [null, name];
  return [null, null];
}

function dateOf(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.exec(value)?.[0] ?? value;
}

export function factsFor(file: DeviceFile, target: string | null, fileName: string | null): Facts {
  const [channel, action] = targetParts(target);
  const entry = channel !== null ? file.write[channel] : action !== null ? file.actions[action] : undefined;
  const confirmed = entry?.confirmed ?? file.confirmed;
  const spec = channel !== null ? file.write[channel] : undefined;
  const limits: Record<string, number> = {};
  if (spec) {
    if (spec.max !== null) limits.max = spec.max;
    if (spec.min !== null) limits.min = spec.min;
    if (spec.max_change_per_s !== null) limits.rate_per_s = spec.max_change_per_s;
  }
  return {
    file: fileName,
    confirmedBy: confirmed?.by ?? null,
    confirmedAt: confirmed ? dateOf(String(confirmed.at)) : null,
    unit: spec?.unit ?? null,
    number: spec?.type === "number",
    limits,
  };
}

export function wireUnit(unit: string | null): string | null {
  if (unit === null) return null;
  return unit.replace(/\bpercent\b/g, "%").replaceAll(" / ", "/");
}

export function quantity(magnitude: number, unit: string): Quantity {
  return { value: magnitude, unit: wireUnit(unit) as string };
}

export function window(seconds: number): Quantity {
  for (const [unit, size] of [["d", 86400], ["h", 3600], ["min", 60]] as const) {
    if (seconds >= size && Number.isInteger(seconds / size)) return quantity(seconds / size, unit);
  }
  return quantity(seconds, "s");
}

export function limitQuantity(kernelCode: string | null, limit: Record<string, unknown> | null): Quantity | null {
  const key = LIMIT_KEYS[kernelCode ?? ""];
  if (!key || !limit || typeof limit[key] !== "number" || !limit.unit) return null;
  const unit = String(limit.unit);
  return quantity(limit[key] as number, key === "rate_per_s" ? `${unit}/s` : unit);
}

export function requestedValue(raw: unknown, unit: string | null, number: boolean): unknown {
  if (raw === undefined || raw === null) return null;
  if (number && unit && typeof raw !== "boolean" && (typeof raw === "string" || typeof raw === "number" || typeof raw === "object")) {
    try {
      return quantity(convert(parseQuantity(raw), unit), unit);
    } catch (error) {
      if (error instanceof UnitError) return typeof raw === "string" ? raw : null;
      throw error;
    }
  }
  if (typeof raw === "string" || typeof raw === "boolean" || typeof raw === "number") return raw;
  return null;
}

function requestedFor(kernelCode: string | null, facts: Facts | null, raw: unknown, limit: Record<string, unknown> | null, about: string | null): unknown {
  if (about === null || raw === undefined || raw === null) return null;
  if (kernelCode === "bad_unit") return typeof raw === "string" || typeof raw === "boolean" || typeof raw === "number" ? raw : null;
  const unit = (limit?.unit as string | undefined) || facts?.unit || null;
  const number = !!limit?.unit || (facts !== null && facts.number);
  return requestedValue(raw, unit, number);
}

function isSessionLimit(facts: Facts, limit: Record<string, unknown> | null): boolean {
  if (!limit) return false;
  return Object.entries(facts.limits).some(([key, own]) => key in limit && own !== limit[key]);
}

const principalName = (label: string | null): string | null => (label ? label.split(":").slice(1).join(":") || label : null);

export interface ErrorFacts {
  device: string | null;
  target?: string | null;
  facts?: Facts | null;
  kernelMessage?: string | null;
  rawValue?: unknown;
  limit?: Record<string, unknown> | null;
  requestId?: string | null;
  principal?: string | null;
}

export function buildError(kernelCode: string | null, input: ErrorFacts): JsonRpcError {
  const facts = input.facts ?? null;
  const [channel, action] = targetParts(input.target ?? null);
  const key = LIMIT_KEYS[kernelCode ?? ""];
  let limit = input.limit ?? null;
  if (limit === null && facts && (key === "max" || key === "min") && key in facts.limits) limit = { [key]: facts.limits[key], unit: facts.unit };
  const argument = typeof limit?.argument === "string" ? limit.argument : null;
  const data: Data = {
    kernelMessage: input.kernelMessage,
    device: input.device,
    channel,
    action,
    argument,
    requested: requestedFor(kernelCode, facts, input.rawValue, limit, channel ?? argument),
    limit: limitQuantity(kernelCode, limit),
    requestId: input.requestId,
  };
  if (limit && "runs" in limit && typeof limit.per_s === "number") {
    data.runs = limit.runs;
    data.per = window(limit.per_s);
  }
  if (limit && limit.interlock) data.interlock = String(limit.interlock);
  if (limit && limit.expected && typeof limit.expected === "object") data.expected = limit.expected;
  if (facts && PROVENANCE_NAMES.has(registryFor(kernelCode).name)) {
    if (isSessionLimit(facts, limit)) data.tightenedBy = principalName(input.principal ?? null) ?? "this client";
    else {
      data.file = facts.file;
      data.confirmedBy = facts.confirmedBy;
      data.confirmedAt = facts.confirmedAt;
    }
  }
  return fromKernel(kernelCode, data);
}

export function bodyValue(command: { kind: string; value?: unknown; unit?: string | null; args?: Record<string, unknown> } | null, limit: Record<string, unknown> | null = null): unknown {
  if (!command) return null;
  if (command.kind === "write") return command.unit === undefined || command.unit === null ? command.value : { value: command.value, unit: command.unit };
  if (limit && limit.argument) return (command.args ?? {})[String(limit.argument)] ?? null;
  return null;
}

export function decisionError(
  decision: Decision,
  file: DeviceFile | undefined,
  command: { kind: string; value?: unknown; unit?: string | null; args?: Record<string, unknown> } | null,
  fileName: string | null,
  principal: string | null = null,
): JsonRpcError {
  return buildError(decision.code, {
    device: decision.device,
    target: decision.target,
    facts: file ? factsFor(file, decision.target, fileName) : null,
    kernelMessage: decision.message,
    rawValue: bodyValue(command, decision.limit),
    limit: decision.limit,
    requestId: decision.request_id,
    principal,
  });
}
