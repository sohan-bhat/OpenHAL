import { type Command, type Decision, type DeviceFile, convert, deviceId, parseQuantity } from "../kernel";
import { normalizeUnit } from "../kernel/units";
import { type Provenance, registryByName, toJsonRpcError } from "../protocol";
import type { TraceEntry } from "../trace";

export function provenanceOf(file: DeviceFile): Provenance {
  return {
    file: `${deviceId(file)}.hal.yaml`,
    confirmedBy: file.confirmed?.by ?? null,
    confirmedAt: file.confirmed?.at ?? null,
  };
}

export function displayUnit(unit: string | null): string | null {
  if (unit === null) return null;
  return normalizeUnit(unit) === "percent" ? "%" : unit;
}

export function requestFor(command: Command): TraceEntry {
  if (command.kind === "write") {
    return { kind: "request", method: "hal/write", params: { device: command.device, channel: command.channel, value: command.value } };
  }
  return { kind: "request", method: "hal/action", params: { device: command.device, action: command.action, args: command.args } };
}

function requestedValue(file: DeviceFile | undefined, command: Command): number | null {
  if (!file || command.kind !== "write") return null;
  const spec = file.write[command.channel];
  if (!spec?.unit) return null;
  try {
    return convert(parseQuantity(command.value), spec.unit);
  } catch {
    return null;
  }
}

export function responseFor(decision: Decision, command: Command, file: DeviceFile | undefined, ttlS = 300): TraceEntry {
  if (decision.status === "blocked" || decision.status === "failed") {
    const error = toJsonRpcError(decision, requestedValue(file, command), file ? provenanceOf(file) : { file: `${decision.device}.hal.yaml`, confirmedBy: null, confirmedAt: null });
    const entry = registryByName(String(error.data.name));
    return { kind: "error", code: entry.code, name: entry.name, reason: error.message };
  }
  if (decision.status === "pending") {
    return { kind: "result", result: { status: "pending", requestId: decision.request_id, expiresInS: ttlS } };
  }
  if (command.kind === "action") return { kind: "result", result: { status: decision.status, result: null } };
  if (decision.status === "allowed" || decision.status === "needs_confirmation") {
    return { kind: "result", result: { status: decision.status, value: decision.value, unit: displayUnit(decision.unit) } };
  }
  return {
    kind: "result",
    result: { status: "done", device: decision.device, channel: command.channel, value: decision.value, unit: displayUnit(decision.unit) },
  };
}
