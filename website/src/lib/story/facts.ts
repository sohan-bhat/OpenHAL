import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { loadScenario, type Exchange, type Scenario } from "../scenario";
import { REPO_ROOT } from "../spec-meta.mjs";
import { reasonLines } from "../trace-html.mjs";
import type { StepId } from "./script";

export interface Refusal {
  name: string;
  code: number;
  reason: string;
}

export interface Ask {
  method: string;
  target: string;
  value: string;
  note: string;
}

export const ASKED = "Keep an eye on my print tonight.";

/** The exchanges of docs/demo/scenario.yaml the story tells, by their ids in the record. */
export const IDS = {
  look: "first-layer",
  bed: "bed-warmer",
  nozzle: "nozzle-too-hot",
  loose: "come-loose",
  pause: "paused",
  cancel: "cancel-waits",
} as const;

export interface StoryFacts {
  printer: { id: string; name: string; driver: string };
  camera: { id: string; channel: string; driver: string; image: string };
  file: string;
  confirmed: string;
  look: Ask;
  loose: Ask;
  bed: Ask & { channel: string; max: string; before: number; after: number; unit: string; status: string };
  nozzle: Ask & { channel: string; max: string; now: string; refusal: Refusal };
  pause: Ask & { status: string };
  cancel: Ask & { status: string; wait: string };
  requests: number;
}

interface Limit {
  unit?: string;
  min?: number;
  max?: number;
}

export interface DeviceFile {
  device: string | { name: string };
  id: string;
  connect: Record<string, unknown>;
  read: Record<string, { unit?: string }>;
  write: Record<string, Limit>;
  actions: Record<string, { confirm?: string } | null>;
}

const NBSP = "\u00a0";
const UNITS: Record<string, string> = { degC: "°C", degF: "°F", percent: "%" };

/** Keeps a number on the same line as its unit. */
export const nb = (text: string): string => text.replace(/(\d) (?=%|°|[a-zA-Z]+\b)/g, `$1${NBSP}`);

/** A unit as a person reads it, `°C` for `degC`. */
export const unitText = (unit: string): string => UNITS[unit] ?? unit;

/** A number and its unit as a person reads them, `300 °C`. */
export function amount(value: unknown, unit: unknown): string {
  const magnitude = Number(value);
  const text = Number.isInteger(magnitude) ? String(magnitude) : String(Number(magnitude.toPrecision(6)));
  return `${text} ${unitText(String(unit ?? ""))}`.trim();
}

/** Message text as a person reads it, with every `degC` written as `°C`. */
export const humane = (text: string): string => text.replace(/(\d) (degC|degF|percent)\b/g, (_, digit: string, unit: string) => `${digit} ${unitText(unit)}`);

export function readDeviceFile(path = join(REPO_ROOT, "examples", "print-babysitter", "printer.hal.yaml")): DeviceFile {
  return parse(readFileSync(path, "utf8")) as DeviceFile;
}

function need<T>(found: T | undefined, what: string): T {
  if (found === undefined) throw new Error(`docs/demo/scenario.yaml has no ${what}, which the landing story shows.`);
  return found;
}

const params = (exchange: Exchange): Record<string, any> => exchange.request.params ?? {};
const statusOf = (exchange: Exchange): string => String(exchange.result?.status ?? "");

function reading(exchange: Exchange, channel: string): { before: number; after: number; unit: string } | null {
  const found = (exchange as Record<string, any>)[channel];
  if (!found?.before || !found?.after) return null;
  return { before: Number(found.before.value), after: Number(found.after.value), unit: String(found.after.unit) };
}

function imageText(exchange: Exchange): string {
  const value = exchange.result?.value ?? exchange.result?.result?.value ?? exchange.result;
  const kind = String(value?.mimeType ?? value?.mime ?? "image");
  return value?.width && value?.height ? `${kind} ${value.width}${NBSP}×${NBSP}${value.height}` : kind;
}

/** Every word and number the landing story shows, from docs/demo/scenario.yaml and the printer's device file. */
export function storyFacts(scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): StoryFacts {
  const record = scenario.record;
  const exchanges = record.exchanges;
  const described = (id: string) => need(record.devices?.find((item) => item.id === id), `description of ${id}`);
  const byId = (id: string) => need(exchanges.find((exchange) => exchange.id === id), `exchange ${id}`);
  const look = byId(IDS.look);
  const loose = byId(IDS.loose);
  const bed = byId(IDS.bed);
  const nozzle = byId(IDS.nozzle);
  const pause = byId(IDS.pause);
  const cancel = byId(IDS.cancel);
  const bedChannel = String(params(bed).channel);
  const nozzleChannel = String(params(nozzle).channel);
  const limit = (channel: string) => amount(file.write[channel]?.max, file.write[channel]?.unit);
  const heated = need(reading(bed, bedChannel) ?? undefined, `${bedChannel} before and after`);
  const printer = described(String(params(bed).device));
  const webcamDevice = described(String(params(look).device));
  const nozzleNow = reading(nozzle, "extruder_temp");
  const error = nozzle.error!;
  const name = typeof file.device === "string" ? file.device : file.device.name;
  const note = (exchange: Exchange) => String(exchange.before ?? "");
  const write = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).channel), value: amount(params(exchange).value, params(exchange).unit), note: note(exchange) });
  const act = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).action), value: "", note: note(exchange) });
  const read = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: `${params(exchange).device} ${params(exchange).channel}`, value: "", note: note(exchange) });
  return {
    printer: { id: printer.id, name, driver: printer.driver },
    camera: { id: webcamDevice.id, channel: String(params(look).channel), driver: webcamDevice.driver, image: imageText(look) },
    file: printer.file,
    confirmed: `confirmed by ${printer.confirmed.by} ${printer.confirmed.at}`,
    look: read(look),
    loose: read(loose),
    bed: { ...write(bed), channel: bedChannel, max: limit(bedChannel), ...heated, status: statusOf(bed) },
    nozzle: {
      ...write(nozzle),
      channel: nozzleChannel,
      max: limit(nozzleChannel),
      now: nozzleNow ? amount(nozzleNow.after, nozzleNow.unit) : "",
      refusal: { name: String(error.data.name), code: Number(error.code), reason: humane(reasonLines(String(error.message))[0]) },
    },
    pause: { ...act(pause), status: statusOf(pause) },
    cancel: { ...act(cancel), status: statusOf(cancel), wait: "waiting for a person" },
    requests: exchanges.length,
  };
}

/** What the story says at each step, in plain words. */
export function storyLines(facts: StoryFacts): Record<StepId, string> {
  const bed = (n: number) => amount(n, facts.bed.unit);
  return {
    intro: "Watch an agent babysit a 3D print.",
    ask: "A long print is running. You ask an agent to keep an eye on it.",
    look: "It looks through the webcam and sees a corner of the first layer lifting.",
    warm: nb(`It warms the bed from ${bed(facts.bed.before)} to ${bed(facts.bed.after)}. That's inside the limit.`),
    hot: nb(`It asks for a ${facts.nozzle.value} nozzle. A person set ${facts.nozzle.max}. The kernel says no.`),
    loose: "Later, the webcam shows the print has come loose.",
    pause: "The agent pauses the print at once.",
    cancel: "Cancelling can't be undone, so the hub asks a person first.",
    wake: "You wake up to a paused print. Cancelling it is your call.",
    end: "Every command to every device takes this path.",
  };
}

export type TraceLine =
  | { kind: "note"; text: string }
  | { kind: "request"; method: string; text: string }
  | { kind: "result"; text: string }
  | { kind: "error"; code: number; name: string; reason: string };

/** The messages each step sends, in the message trace's shape, with numbers as a person reads them. */
export function storyTrace(facts: StoryFacts): Partial<Record<StepId, TraceLine[]>> {
  const out = (ask: Ask): TraceLine[] => [
    ...(ask.note ? [{ kind: "note" as const, text: ask.note }] : []),
    { kind: "request", method: ask.method, text: nb([ask.target, ask.value].filter(Boolean).join(" ")) },
  ];
  const image: TraceLine = { kind: "result", text: facts.camera.image };
  const { refusal } = facts.nozzle;
  return {
    look: [...out(facts.look), image],
    warm: [...out(facts.bed), { kind: "result", text: facts.bed.status }],
    hot: [...out(facts.nozzle), { kind: "error", code: refusal.code, name: refusal.name, reason: nb(refusal.reason) }],
    loose: [...out(facts.loose), image],
    pause: [...out(facts.pause), { kind: "result", text: facts.pause.status }],
    cancel: [...out(facts.cancel), { kind: "result", text: facts.cancel.status }],
    ask: [{ kind: "note", text: "nothing sent to the hub yet" }],
    wake: [{ kind: "note", text: `${facts.cancel.wait}: ${facts.cancel.target} on ${facts.printer.id}` }],
    end: [{ kind: "note", text: `${facts.requests} requests, every one through the hub and its kernel` }],
  };
}
