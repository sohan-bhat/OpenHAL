import type { Decision, DeviceFile } from "./kernel";
import { UnitError, convert, formatQuantity, parseQuantity } from "./kernel/units";

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

const has = (data: Data, key: string): boolean => data[key] !== undefined && data[key] !== null && data[key] !== "" && data[key] !== false;

function subject(data: Data): string {
  if (has(data, "channel")) return [data.channel, data.requested].filter((part) => part !== undefined && part !== null).map(String).join(" ");
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
  const text = `${subject(data)} ${verb} the ${tightened ? "session limit" : "limit"} of ${data.limit}`;
  return text + (tightened ? session(data) : provenance(data));
}

function rateLimited(data: Data): string {
  if (!has(data, "limit")) return `${subject(data)} changes faster than allowed right now${provenance(data)}`;
  if (has(data, "tightenedBy")) return `${subject(data)} changes faster than the session limit of ${data.limit} allows right now${session(data)}`;
  return `${subject(data)} changes faster than ${data.limit} allows right now${provenance(data)}`;
}

function invalidValue(data: Data): string {
  if (data.kernelCode === "bad_step" && has(data, "limit")) return `${subject(data)} is not a step of ${data.limit}${provenance(data)}`;
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
          ? `Only a human can call ${data.method}`
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
    template: (data) => `${subject(data)} is held back by an interlock or requirement that doesn't hold${provenance(data)}`,
  },
  {
    code: -32013,
    name: "CONFIRMATION_REQUIRED",
    kernelCodes: ["needs_confirmation"],
    meaning: "Queued for a person, data.requestId names the request",
    template: (data) =>
      has(data, "requestId") ? `${subject(data)} waits for a person to approve request ${data.requestId}` : `${subject(data)} needs a person to approve it`,
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
    template: (data) => `${subject(data)} needs a finite number with a unit it can convert${provenance(data)}`,
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

export function limitText(kernelCode: string | null, limit: Record<string, unknown> | null): string | null {
  const key = LIMIT_KEYS[kernelCode ?? ""];
  if (!key || !limit || typeof limit[key] !== "number" || !limit.unit) return null;
  const text = formatQuantity(limit[key] as number, String(limit.unit));
  return key === "rate_per_s" ? `${text}/s` : text;
}

export function requestedText(facts: Facts | null, raw: unknown): string | null {
  if (raw === undefined || raw === null) return null;
  if (facts?.number && facts.unit && (typeof raw === "string" || (typeof raw === "object" && raw !== null))) {
    try {
      return formatQuantity(convert(parseQuantity(raw as string), facts.unit), facts.unit);
    } catch (error) {
      if (error instanceof UnitError) return String(raw);
      throw error;
    }
  }
  if (typeof raw === "boolean") return String(raw);
  return String(raw);
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
  const data: Data = {
    kernelMessage: input.kernelMessage,
    device: input.device,
    channel,
    action,
    requested: channel !== null ? requestedText(facts, input.rawValue) : null,
    limit: limitText(kernelCode, limit),
    requestId: input.requestId,
  };
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

export function decisionError(decision: Decision, file: DeviceFile | undefined, rawValue: unknown, fileName: string | null, principal: string | null = null): JsonRpcError {
  return buildError(decision.code, {
    device: decision.device,
    target: decision.target,
    facts: file ? factsFor(file, decision.target, fileName) : null,
    kernelMessage: decision.message,
    rawValue,
    limit: decision.limit,
    requestId: decision.request_id,
    principal,
  });
}
