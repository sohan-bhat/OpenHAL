import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { loadScenario, type Exchange, type Scenario } from "../scenario";
import { REPO_ROOT } from "../spec-meta.mjs";
import { reasonLines } from "../trace-html.mjs";
import type { ShotId } from "./script";

export interface Refusal {
  name: string;
  code: number;
  reason: string;
}

export interface Ask {
  method: string;
  target: string;
  value: string;
}

export interface StoryFacts {
  printer: { id: string; name: string; driver: string };
  camera: { id: string; channel: string; image: string };
  file: string;
  confirmed: string;
  look: Ask;
  bed: Ask & { channel: string; max: string; before: number; after: number; unit: string; status: string };
  nozzle: Ask & { channel: string; max: string; now: string; refusal: Refusal };
  pause: Ask & { status: string };
  cancel: Ask & { status: string; wait: string };
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
  return value?.width && value?.height ? `${kind} ${value.width} × ${value.height}` : kind;
}

/** Every word and number the landing story shows, from docs/demo/scenario.yaml and the printer's device file. */
export function storyFacts(scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): StoryFacts {
  const record = scenario.record as Scenario["record"] & { confirmed: { by: string; at: string } };
  const exchanges = record.exchanges;
  const reads = exchanges.filter((exchange) => exchange.request.method === "hal/read");
  const look = need(reads[0], "camera read");
  const writes = exchanges.filter((exchange) => exchange.request.method === "hal/write");
  const bed = need(writes.find((exchange) => exchange.result), "granted write");
  const nozzle = need(writes.find((exchange) => exchange.error), "refused write");
  const actions = exchanges.filter((exchange) => exchange.request.method === "hal/action");
  const pause = need(actions.find((exchange) => statusOf(exchange) === "done"), "action that ran");
  const cancel = need(actions.find((exchange) => statusOf(exchange) === "pending"), "action that waits for a person");
  const bedChannel = String(params(bed).channel);
  const nozzleChannel = String(params(nozzle).channel);
  const limit = (channel: string) => amount(file.write[channel]?.max, file.write[channel]?.unit);
  const heated = reading(bed, "bed_temp") ?? { before: Number(params(bed).value), after: Number(params(bed).value), unit: String(params(bed).unit) };
  const nozzleNow = reading(nozzle, "extruder_temp");
  const error = nozzle.error!;
  const name = typeof file.device === "string" ? file.device : file.device.name;
  const write = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).channel), value: amount(params(exchange).value, params(exchange).unit) });
  const act = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).action), value: "" });
  return {
    printer: { id: file.id, name, driver: Object.keys(file.connect)[0] },
    camera: { id: String(params(look).device), channel: String(params(look).channel), image: imageText(look) },
    file: scenario.file ?? "",
    confirmed: `confirmed by ${record.confirmed.by} ${record.confirmed.at}`,
    look: { method: look.request.method, target: `${params(look).device} ${params(look).channel}`, value: "" },
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
  };
}

/** What the story says at each shot, in plain words. */
export function storyLines(facts: StoryFacts): Record<ShotId, string> {
  const bed = (n: number) => amount(n, facts.bed.unit);
  return {
    wide: "Watch an agent babysit a 3D print.",
    watch: "A long print is running. You ask an agent to keep an eye on it.",
    look: "It looks through the camera and sees a corner of the first layer lifting.",
    warm: nb(`It asks to warm the bed from ${bed(facts.bed.before)} to ${bed(facts.bed.after)}. That's inside the limit.`),
    heat: nb(`So it happens. The bed warms to ${bed(facts.bed.after)}.`),
    hot: nb(`Then it asks for a ${facts.nozzle.value} nozzle. A person capped it at ${facts.nozzle.max}.`),
    reply: "The kernel says no and tells the agent why. The nozzle never changed.",
    loose: "Later, the camera shows the print has come loose.",
    pause: "The agent pauses the print at once.",
    cancel: "Cancelling can't be undone, so the hub asks a person first.",
    wake: "You wake up to a paused print and one question.",
    end: "Every command to every device takes this path.",
  };
}
