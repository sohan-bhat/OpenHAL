import { fromKernelCode } from "./protocol";
import type { Decision, DeviceSummary, DeviceView } from "./types";
import { formatQuantity } from "./units";

export interface ReadingEvent {
  type: "reading";
  device: string;
  channel: string;
  value: unknown;
  unit: string | null;
  at?: number;
  suspect?: boolean;
}

export function applyReading(view: DeviceView, event: ReadingEvent): DeviceView {
  if (view.id !== event.device) return view;
  const live = { value: event.value, known: true, age_s: 0 };
  if (event.channel in view.read) {
    return { ...view, read: { ...view.read, [event.channel]: { ...view.read[event.channel]!, ...live } } };
  }
  if (event.channel in view.write) {
    return { ...view, write: { ...view.write, [event.channel]: { ...view.write[event.channel]!, ...live } } };
  }
  return view;
}

export function sortDevices(devices: DeviceSummary[]): DeviceSummary[] {
  return [...devices].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

export type DecisionTone = "granted" | "pending" | "blocked" | "failed";

export interface DecisionSummary {
  tone: DecisionTone;
  word: string;
  head: string;
  reason: string;
}

export function describeDecision(decision: Decision): DecisionSummary {
  const entry = fromKernelCode(decision.code);
  const head = entry ? `${entry.code} ${entry.name}` : decision.code ?? "";
  if (decision.status === "done" || decision.status === "allowed") {
    const shown = decision.value === null || decision.value === undefined ? "" : formatQuantity(decision.value, decision.unit);
    return {
      tone: "granted",
      word: decision.status === "done" ? "granted" : "allowed",
      head: shown,
      reason: decision.message,
    };
  }
  if (decision.status === "pending" || decision.status === "needs_confirmation") {
    return { tone: "pending", word: "confirmation required", head, reason: decision.message };
  }
  if (decision.status === "failed") return { tone: "failed", word: "failed", head, reason: decision.message };
  return { tone: "blocked", word: "blocked", head, reason: decision.message };
}

export function isSimulated(device: { simulated?: boolean }): boolean {
  return device.simulated === true;
}
