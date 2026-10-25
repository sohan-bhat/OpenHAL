import type { Decision } from "./kernel";
import { formatQuantity } from "./kernel/units";

export interface RegistryEntry {
  code: number;
  name: string;
  kernelCodes: string[];
}

export const ERROR_REGISTRY: RegistryEntry[] = [
  { code: -32700, name: "PARSE_ERROR", kernelCodes: [] },
  { code: -32600, name: "INVALID_REQUEST", kernelCodes: [] },
  { code: -32601, name: "METHOD_NOT_FOUND", kernelCodes: [] },
  { code: -32602, name: "INVALID_PARAMS", kernelCodes: ["bad_request"] },
  { code: -32603, name: "INTERNAL_ERROR", kernelCodes: ["internal_error"] },
  { code: -32001, name: "NOT_INITIALIZED", kernelCodes: [] },
  { code: -32002, name: "UNAUTHORIZED", kernelCodes: [] },
  { code: -32003, name: "SCOPE_DENIED", kernelCodes: ["not_permitted"] },
  { code: -32004, name: "UNKNOWN_TARGET", kernelCodes: ["unknown_target"] },
  { code: -32005, name: "DEVICE_UNAVAILABLE", kernelCodes: ["device_unavailable"] },
  { code: -32010, name: "LIMIT_EXCEEDED", kernelCodes: ["above_max", "below_min"] },
  { code: -32011, name: "RATE_LIMITED", kernelCodes: ["rate_limited"] },
  { code: -32012, name: "INTERLOCK_BLOCKED", kernelCodes: ["interlock"] },
  { code: -32013, name: "CONFIRMATION_REQUIRED", kernelCodes: ["needs_confirmation"] },
  { code: -32014, name: "STOPPED", kernelCodes: ["stopped"] },
  { code: -32015, name: "UNVERIFIED_LIMITS", kernelCodes: ["read_only_file"] },
  { code: -32016, name: "INVALID_VALUE", kernelCodes: ["bad_value", "bad_step"] },
  { code: -32017, name: "WATCHDOG_TRIPPED", kernelCodes: ["duration_exceeded"] },
  { code: -32018, name: "BUSY", kernelCodes: ["busy"] },
  { code: -32019, name: "QUEUE_FULL", kernelCodes: ["queue_full"] },
  { code: -32020, name: "DRIVER_ERROR", kernelCodes: ["driver_error"] },
  { code: -32021, name: "MISCONFIGURED", kernelCodes: ["misconfigured", "cannot_loosen"] },
  { code: -32022, name: "REQUEST_CLOSED", kernelCodes: ["expired", "rejected"] },
  { code: -32023, name: "UNIT_INVALID", kernelCodes: ["bad_unit"] },
];

export function registryFor(kernelCode: string): RegistryEntry {
  const entry = ERROR_REGISTRY.find((item) => item.kernelCodes.includes(kernelCode));
  if (!entry) throw new Error(`No registry entry for kernel code ${kernelCode}.`);
  return entry;
}

export function registryByName(name: string): RegistryEntry {
  const entry = ERROR_REGISTRY.find((item) => item.name === name);
  if (!entry) throw new Error(`No registry entry named ${name}.`);
  return entry;
}

export interface Provenance {
  file: string;
  confirmedBy: string | null;
  confirmedAt: string | null;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data: Record<string, unknown>;
}

function provenanceText(source: Provenance): string {
  const confirmed = source.confirmedBy ? `, confirmed by ${source.confirmedBy}${source.confirmedAt ? ` ${source.confirmedAt}` : ""}` : "";
  return `(${source.file}${confirmed})`;
}

export function reasonFor(name: string, decision: Decision, requested: number | null, source: Provenance): string {
  const limit = decision.limit as Record<string, number | string> | null;
  const channel = decision.target.replace(/^write:|^action:/, "");
  if (name === "LIMIT_EXCEEDED" && limit && requested !== null && typeof limit.unit === "string") {
    const bound = typeof limit.max === "number" ? limit.max : (limit.min as number);
    const verb = typeof limit.max === "number" ? "exceeds the limit of" : "is below the limit of";
    return `${channel} ${formatQuantity(requested, limit.unit)} ${verb} ${formatQuantity(bound, limit.unit)} ${provenanceText(source)}`;
  }
  return decision.message;
}

export function toJsonRpcError(decision: Decision, requested: number | null, source: Provenance): JsonRpcError {
  const entry = registryFor(decision.code ?? "internal_error");
  const limit = decision.limit as Record<string, unknown> | null;
  const data: Record<string, unknown> = {
    name: entry.name,
    kernelCode: decision.code,
    device: decision.device,
  };
  if (decision.target.startsWith("write:")) data.channel = decision.target.slice(6);
  if (limit) data.limit = limit;
  if (requested !== null) data.requested = requested;
  data.file = source.file;
  if (source.confirmedBy) data.confirmedBy = source.confirmedBy;
  if (source.confirmedAt) data.confirmedAt = source.confirmedAt;
  if (decision.request_id) data.requestId = decision.request_id;
  data.kernelMessage = decision.message;
  return { code: entry.code, message: reasonFor(entry.name, decision, requested, source), data };
}
