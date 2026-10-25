import versions from "../../../spec/versions.json";

export const PROTOCOL_VERSION: string = (versions as { latest: string }).latest;

export interface RegistryEntry {
  code: number;
  name: string;
  kernelCodes: string[];
  meaning: string;
}

export const REGISTRY: RegistryEntry[] = [
  { code: -32700, name: "PARSE_ERROR", kernelCodes: [], meaning: "Invalid JSON" },
  { code: -32600, name: "INVALID_REQUEST", kernelCodes: [], meaning: "Not a JSON-RPC request" },
  { code: -32601, name: "METHOD_NOT_FOUND", kernelCodes: [], meaning: "Unknown method, or one above the hub's conformance level" },
  { code: -32602, name: "INVALID_PARAMS", kernelCodes: ["bad_request"], meaning: "Params don't match the schema" },
  { code: -32603, name: "INTERNAL_ERROR", kernelCodes: ["internal_error"], meaning: "A bug in the hub" },
  { code: -32001, name: "NOT_INITIALIZED", kernelCodes: [], meaning: "hal/initialize hasn't run" },
  { code: -32002, name: "UNAUTHORIZED", kernelCodes: [], meaning: "Missing or unknown token" },
  { code: -32003, name: "SCOPE_DENIED", kernelCodes: ["not_permitted"], meaning: "The principal's token scope doesn't cover this device or method" },
  { code: -32004, name: "UNKNOWN_TARGET", kernelCodes: ["unknown_target"], meaning: "No such device, channel or action" },
  { code: -32005, name: "DEVICE_UNAVAILABLE", kernelCodes: ["device_unavailable"], meaning: "Disconnected or not ready" },
  { code: -32010, name: "LIMIT_EXCEEDED", kernelCodes: ["above_max", "below_min"], meaning: "Outside the device file's confirmed limits" },
  { code: -32011, name: "RATE_LIMITED", kernelCodes: ["rate_limited"], meaning: "Faster than max_change_per_s allows right now" },
  { code: -32012, name: "INTERLOCK_BLOCKED", kernelCodes: ["interlock"], meaning: "An interlock or action requirement doesn't hold, or a value it needs is unknown" },
  { code: -32013, name: "CONFIRMATION_REQUIRED", kernelCodes: ["needs_confirmation"], meaning: "Queued for a person" },
  { code: -32014, name: "STOPPED", kernelCodes: ["stopped"], meaning: "The hub is stopped until a person unlocks" },
  { code: -32015, name: "UNVERIFIED_LIMITS", kernelCodes: ["read_only_file"], meaning: "The device file's limits aren't confirmed by a person, so it is read-only" },
  { code: -32016, name: "INVALID_VALUE", kernelCodes: ["bad_value", "bad_step"], meaning: "Wrong type, step, enum value or pattern" },
  { code: -32017, name: "WATCHDOG_TRIPPED", kernelCodes: ["duration_exceeded"], meaning: "A watchdog budget is used up" },
  { code: -32018, name: "BUSY", kernelCodes: ["busy"], meaning: "Another command holds the device" },
  { code: -32019, name: "QUEUE_FULL", kernelCodes: ["queue_full"], meaning: "The confirmation queue is full" },
  { code: -32020, name: "DRIVER_ERROR", kernelCodes: ["driver_error"], meaning: "The device or its protocol failed, and the channel is unknown until a readback" },
  { code: -32021, name: "MISCONFIGURED", kernelCodes: ["misconfigured", "cannot_loosen"], meaning: "The hub's device files are inconsistent, or a change would loosen a confirmed limit" },
  { code: -32022, name: "REQUEST_CLOSED", kernelCodes: ["expired", "rejected"], meaning: "The confirmation request expired or was rejected" },
  { code: -32023, name: "UNIT_INVALID", kernelCodes: ["bad_unit"], meaning: "A missing, unknown or incompatible unit, or a value that isn't finite" },
];

const byKernel = new Map<string, RegistryEntry>();
const byCode = new Map<number, RegistryEntry>();
const byName = new Map<string, RegistryEntry>();
for (const entry of REGISTRY) {
  byCode.set(entry.code, entry);
  byName.set(entry.name, entry);
  for (const kernel of entry.kernelCodes) byKernel.set(kernel, entry);
}

export function fromKernelCode(kernelCode: string | null | undefined): RegistryEntry | undefined {
  return kernelCode ? byKernel.get(kernelCode) : undefined;
}

export function fromCode(code: number | null | undefined): RegistryEntry | undefined {
  return code === null || code === undefined ? undefined : byCode.get(code);
}

export function fromName(name: string | null | undefined): RegistryEntry | undefined {
  return name ? byName.get(name) : undefined;
}

export function errorLabel(code: number, name: string | undefined): string {
  return name ? `error ${code} ${name}` : `error ${code}`;
}

export const METHODS = [
  "hal/initialize",
  "hal/devices/list",
  "hal/devices/describe",
  "hal/read",
  "hal/readMany",
  "hal/write",
  "hal/dryRun",
  "hal/planCheck",
  "hal/stop",
  "hal/unlock",
  "hal/action",
  "hal/confirmations/list",
  "hal/confirmations/approve",
  "hal/confirmations/reject",
  "hal/routines/list",
  "hal/routines/dryRun",
  "hal/audit/query",
] as const;

export const NOTIFICATIONS = [
  "hal/initialized",
  "hal/shutdown",
  "hal/value",
  "hal/blocked",
  "hal/stopped",
  "hal/deviceAdded",
  "hal/deviceRemoved",
  "hal/confirmationRequested",
] as const;

export type Conformance = "core" | "control" | "full";

const CORE_DRIVERS = new Set(["uvc", "rpi-camera"]);

export function conformanceFor(device: { conformance?: string | null; driver: string }): Conformance {
  const given = device.conformance;
  if (given === "core" || given === "control" || given === "full") return given;
  return CORE_DRIVERS.has(device.driver) ? "core" : "control";
}
