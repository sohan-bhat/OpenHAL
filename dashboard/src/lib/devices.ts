import { fromKernelCode } from "./protocol";
import { compareText } from "./text";
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
  const current = view.read[event.channel] ?? view.write[event.channel];
  if (current && current.known && current.age_s === 0 && JSON.stringify(current.value) === JSON.stringify(event.value)) return view;
  const live = { value: event.value, known: true, age_s: 0 };
  if (event.channel in view.read) {
    return { ...view, read: { ...view.read, [event.channel]: { ...view.read[event.channel]!, ...live } } };
  }
  if (event.channel in view.write) {
    return { ...view, write: { ...view.write, [event.channel]: { ...view.write[event.channel]!, ...live } } };
  }
  return view;
}

export interface Camera {
  device: string;
  channel: string;
  name: string;
}

export function imageChannels(view: DeviceView): string[] {
  return Object.entries(view.read)
    .filter(([, spec]) => spec.type === "image")
    .map(([name]) => name);
}

export function camerasFor(device: string, views: Record<string, DeviceView>): Camera[] {
  const own = views[device];
  const cameras = (view: DeviceView) => imageChannels(view).map((channel) => ({ device: view.id, channel, name: view.name }));
  const others = Object.values(views)
    .filter((view) => view.id !== device)
    .sort((a, b) => compareText(a.name, b.name) || compareText(a.id, b.id));
  return [...(own ? cameras(own) : []), ...others.flatMap(cameras)];
}

export function sortDevices(devices: DeviceSummary[]): DeviceSummary[] {
  return [...devices].sort((a, b) => compareText(a.name, b.name) || compareText(a.id, b.id));
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
