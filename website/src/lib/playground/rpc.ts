import { type Command, type Decision, type DeviceFile, deviceId } from "../kernel";
import { normalizeUnit } from "../kernel/units";
import { type JsonRpcError, decisionError, quantity, wireUnit } from "../protocol";
import type { TraceEntry } from "../trace";

export function fileNameOf(file: DeviceFile): string {
  return `${deviceId(file)}.hal.yaml`;
}

export function displayUnit(unit: string | null): string | null {
  if (unit === null) return null;
  return normalizeUnit(unit) === "percent" ? "%" : unit;
}

function wireArgument(value: unknown): unknown {
  if (value !== null && typeof value === "object" && "value" in value && (value as { unit?: unknown }).unit) {
    const item = value as { value: number; unit: string };
    return { value: item.value, unit: String(item.unit) };
  }
  if (typeof value === "string" || typeof value === "boolean") return value;
  return String(value);
}

export function commandParams(command: Command): Record<string, unknown> {
  if (command.kind === "write") {
    const params: Record<string, unknown> = { device: command.device, channel: command.channel, value: command.value };
    if (command.unit !== undefined && command.unit !== null) params.unit = command.unit;
    return params;
  }
  return { device: command.device, action: command.action, args: Object.fromEntries(Object.entries(command.args).map(([name, value]) => [name, wireArgument(value)])) };
}

export function requestFor(command: Command): TraceEntry {
  return { kind: "request", method: command.kind === "write" ? "hal/write" : "hal/action", params: commandParams(command) };
}

export function actionArgs(file: DeviceFile | undefined, action: string, args: unknown): Record<string, unknown> {
  if (args === null || typeof args !== "object" || Array.isArray(args)) return {};
  const spec = file?.actions[action];
  const out: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(args as Record<string, unknown>)) {
    const arg = spec?.args[name];
    out[name] = arg?.unit && typeof value === "number" ? quantity(value, arg.unit) : value;
  }
  return out;
}

export function errorFor(decision: Decision, command: Command, file: DeviceFile | undefined, principal: string | null = null): JsonRpcError {
  return decisionError(decision, file, command, file ? fileNameOf(file) : `${decision.device}.hal.yaml`, principal);
}

export function decisionWire(decision: Decision, command: Command, file: DeviceFile | undefined, principal: string | null = null): Record<string, unknown> {
  const channel = decision.target.startsWith("write:") ? decision.target.slice(6) : null;
  const action = decision.target.startsWith("action:") ? decision.target.slice(7) : null;
  const unit = decision.unit ?? (channel !== null && file && channel in file.write ? file.write[channel].unit : null);
  let value = decision.value ?? null;
  if (action !== null && value !== null) value = actionArgs(file, action, value);
  const wire: Record<string, unknown> = { status: decision.status, device: decision.device, target: decision.target, value, unit: wireUnit(unit) };
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
    return { kind: "result", result: { status: "done", result: { device: decision.device, action: command.action, args: actionArgs(file, command.action, decision.value) } } };
  }
  return { kind: "result", result: { status: "done", device: decision.device, channel: command.channel, value: decision.value ?? null, unit: wireUnit(decision.unit) } };
}
