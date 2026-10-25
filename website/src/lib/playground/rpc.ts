import { type Command, type Decision, type DeviceFile, deviceId } from "../kernel";
import { normalizeUnit } from "../kernel/units";
import { type JsonRpcError, decisionError } from "../protocol";
import type { TraceEntry } from "../trace";

export function fileNameOf(file: DeviceFile): string {
  return `${deviceId(file)}.hal.yaml`;
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

export function errorFor(decision: Decision, command: Command, file: DeviceFile | undefined, principal: string | null = null): JsonRpcError {
  return decisionError(decision, file, command.kind === "write" ? command.value : null, file ? fileNameOf(file) : `${decision.device}.hal.yaml`, principal);
}

export function decisionWire(decision: Decision, command: Command, file: DeviceFile | undefined, principal: string | null = null): Record<string, unknown> {
  const [channel] = decision.target.startsWith("write:") ? [decision.target.slice(6)] : [null];
  const unit = decision.unit ?? (channel !== null && file && channel in file.write ? file.write[channel].unit : null);
  const wire: Record<string, unknown> = { status: decision.status, device: decision.device, target: decision.target, value: decision.value ?? null, unit };
  if (decision.status === "blocked" || decision.status === "failed") wire.error = errorFor(decision, command, file, principal);
  if (decision.request_id) wire.requestId = decision.request_id;
  return wire;
}

export function errorEntry(error: JsonRpcError): TraceEntry {
  return { kind: "error", code: error.code, name: String(error.data.name), reason: error.message };
}

export function responseFor(decision: Decision, command: Command, file: DeviceFile | undefined, ttlS = 300, principal: string | null = null): TraceEntry {
  if (decision.status === "blocked" || decision.status === "failed") return errorEntry(errorFor(decision, command, file, principal));
  if (decision.status === "pending") {
    return { kind: "result", result: { status: "pending", requestId: decision.request_id, expiresInS: ttlS } };
  }
  if (command.kind === "action") {
    const args = decision.value && typeof decision.value === "object" ? decision.value : {};
    return { kind: "result", result: { status: "done", result: { device: decision.device, action: command.action, args } } };
  }
  return { kind: "result", result: { status: "done", device: decision.device, channel: command.channel, value: decision.value ?? null, unit: decision.unit } };
}
