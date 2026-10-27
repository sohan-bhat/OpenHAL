import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { loadScenario, type Exchange, type Scenario } from "../scenario";
import { REPO_ROOT } from "../spec-meta.mjs";
import { reasonLines } from "../trace-html.mjs";
import { PLACED, type StepId } from "./script";
import type { Tone, TraceLine } from "./trace";

export type { TraceLine } from "./trace";

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

export interface Check {
  name: string;
  word: string;
}

export type VerdictKind = "idle" | "granted" | "blocked" | "confirm";

export interface Verdict {
  kind: VerdictKind;
  text: string;
}

export interface KernelView {
  reading: boolean;
  checks: Check[];
  verdict: Verdict;
}

export interface Reading {
  name: string;
  word: boolean;
  at: Record<StepId, string>;
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
  approve: "owner-approves",
} as const;

/** The exchange each step tells. The title, the ask and the ending send nothing. */
export const TOLD: Partial<Record<StepId, keyof typeof IDS>> = {
  look: "look",
  warm: "bed",
  hot: "nozzle",
  loose: "loose",
  pause: "pause",
  cancel: "cancel",
  approve: "approve",
};

export interface StoryFacts {
  printer: { id: string; name: string; driver: string; readings: Reading[] };
  camera: { id: string; channel: string; driver: string; image: string };
  file: string;
  confirmed: string;
  look: Ask;
  loose: Ask;
  bed: Ask & { channel: string; max: string; before: number; after: number; unit: string; status: string };
  nozzle: Ask & { channel: string; max: string; refusal: Refusal };
  pause: Ask & { status: string };
  cancel: Ask & { status: string; rule: string };
  approve: Ask & { device: string; status: string; approved: string };
  kernel: Record<StepId, KernelView>;
  audit: { counts: string };
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

const NBSP = " ";
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

/** A principal as the record names it, `human:owner`, as a person reads it, `owner`. */
export const named = (principal: string): string => principal.slice(principal.indexOf(":") + 1);

const capital = (word: string): string => `${word[0].toUpperCase()}${word.slice(1)}`;

export function readDeviceFile(path = join(REPO_ROOT, "examples", "print-babysitter", "printer.hal.yaml")): DeviceFile {
  return parse(readFileSync(path, "utf8")) as DeviceFile;
}

function need<T>(found: T | undefined | null, what: string): T {
  if (found === undefined || found === null) throw new Error(`docs/demo/scenario.yaml has no ${what}, which the landing story shows.`);
  return found;
}

const params = (exchange: Exchange): Record<string, any> => exchange.request.params ?? {};
const statusOf = (exchange: Exchange): string => String(exchange.result?.status ?? "");
const field = (exchange: Exchange, key: string): any => (exchange as Record<string, any>)[key];

function imageText(exchange: Exchange): string {
  const value = exchange.result?.value ?? exchange.result?.result?.value ?? exchange.result;
  const kind = String(value?.mimeType ?? value?.mime ?? "image");
  return value?.width && value?.height ? `${kind} ${value.width}${NBSP}×${NBSP}${value.height}` : kind;
}

const TONES: Record<string, Tone> = { done: "ok", pending: "pending", blocked: "blocked", failed: "blocked" };

/** What the kernel did with a step's request, in the record's words, and the verdict it reached. */
function kernelView(exchange: Exchange | undefined, id: string): KernelView {
  if (!exchange) return { reading: false, checks: [], verdict: { kind: "idle", text: "Waiting for a command" } };
  const kernel = need(field(exchange, "kernel"), `kernel record for ${id}`);
  const checks: Check[] = Object.entries(need(kernel.checks as Record<string, string>, `kernel checks for ${id}`)).map(([name, word]) => ({ name: capital(name), word: String(word) }));
  const reading = exchange.request.method === "hal/read";
  if (reading) {
    checks.push({ name: "Grant", word: String(kernel.grant) });
    checks.push({ name: "Audit log", word: `entry ${need(kernel.logged as number[], `log entry for ${id}`).join(", ")}` });
  }
  const words = checks.map((check) => check.word);
  const verdict: Verdict | undefined = exchange.error
    ? { kind: "blocked", text: String(exchange.error.data.name) }
    : words.includes("required")
      ? { kind: "confirm", text: "confirmation required" }
      : kernel.grant === "issued"
        ? { kind: "granted", text: "granted" }
        : reading && kernel.grant === "not needed"
          ? { kind: "granted", text: "allowed" }
          : undefined;
  return { reading, checks, verdict: need(verdict, `kernel verdict for ${id}`) };
}

/** Every word and number the landing story shows, from docs/demo/scenario.yaml and the printer's device file. */
export function storyFacts(scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): StoryFacts {
  const record = scenario.record;
  const exchanges = record.exchanges;
  const described = (id: string) => need(record.devices?.find((item) => item.id === id), `description of ${id}`);
  const byId = (id: string) => need(exchanges.find((exchange) => exchange.id === id), `exchange ${id}`);
  const told = (step: StepId) => (TOLD[step] ? byId(IDS[TOLD[step]!]) : undefined);
  const look = byId(IDS.look);
  const loose = byId(IDS.loose);
  const bed = byId(IDS.bed);
  const nozzle = byId(IDS.nozzle);
  const pause = byId(IDS.pause);
  const cancel = byId(IDS.cancel);
  const approve = byId(IDS.approve);
  const bedChannel = String(params(bed).channel);
  const nozzleChannel = String(params(nozzle).channel);
  const limit = (channel: string) => amount(file.write[channel]?.max, file.write[channel]?.unit);
  const change = need(field(bed, bedChannel), `${bedChannel} before and after`);
  const printer = described(String(params(bed).device));
  const webcamDevice = described(String(params(look).device));
  const error = need(nozzle.error, `error for ${IDS.nozzle}`);
  const name = typeof file.device === "string" ? file.device : file.device.name;
  const note = (exchange: Exchange) => String(need(exchange.before, `narration for ${exchange.id}`));
  const write = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).channel), value: amount(params(exchange).value, params(exchange).unit), note: note(exchange) });
  const act = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).action), value: "", note: note(exchange) });
  const read = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: `${params(exchange).device} ${params(exchange).channel}`, value: "", note: note(exchange) });
  const viewed = exchanges.filter((exchange) => field(exchange, "printer"));
  const viewAt = (step: StepId): Record<string, any> => {
    const own = told(step);
    if (own) return need(field(own, "printer"), `printer view after ${own.id}`);
    const next = PLACED.slice(PLACED.findIndex((item) => item.id === step)).map((item) => told(item.id)).find(Boolean);
    return field(next ?? viewed[viewed.length - 1], "printer") ?? {};
  };
  const readingAt = (what: string, pick: (view: Record<string, any>) => string | undefined): Record<StepId, string> =>
    Object.fromEntries(PLACED.map((item) => [item.id, need(pick(viewAt(item.id)), `${what} for the story's ${item.id} step`)])) as Record<StepId, string>;
  const quantity = (key: string) => (view: Record<string, any>) => (view[key] ? amount(view[key].value, view[key].unit) : undefined);
  const readings: Reading[] = [
    { name: "Nozzle", word: false, at: readingAt("the nozzle temperature", quantity("extruder_temp")) },
    { name: "Bed target", word: false, at: readingAt("the bed target", quantity(bedChannel)) },
    { name: "State", word: true, at: readingAt("the printer state", (view) => view.state) },
  ];
  const approved = String(need(field(approve, "kernel")?.approved_by, `approver of ${IDS.approve}`));
  const audit = need((record as Record<string, any>).audit, "audit log");
  const counts = Object.entries(need(audit.counts as Record<string, number>, "audit counts")).map(([key, count]) => `${count} ${key.replaceAll("_", " ")}`);
  const approvedTarget = String(need(approve.result?.target, `target of ${IDS.approve}`));
  return {
    printer: { id: printer.id, name, driver: printer.driver, readings },
    camera: { id: webcamDevice.id, channel: String(params(look).channel), driver: webcamDevice.driver, image: imageText(look) },
    file: printer.file,
    confirmed: `confirmed by ${printer.confirmed.by} ${printer.confirmed.at}`,
    look: read(look),
    loose: read(loose),
    bed: { ...write(bed), channel: bedChannel, max: limit(bedChannel), before: Number(change.before.value), after: Number(change.after.value), unit: String(change.after.unit), status: statusOf(bed) },
    nozzle: {
      ...write(nozzle),
      channel: nozzleChannel,
      max: limit(nozzleChannel),
      refusal: { name: String(error.data.name), code: Number(error.code), reason: humane(reasonLines(String(error.message))[0]) },
    },
    pause: { ...act(pause), status: statusOf(pause) },
    cancel: { ...act(cancel), status: statusOf(cancel), rule: `${capital(String(params(cancel).action))} waits for a person` },
    approve: {
      method: approve.request.method,
      target: approvedTarget.slice(approvedTarget.indexOf(":") + 1),
      device: String(approve.result?.device),
      value: "",
      note: note(approve),
      status: statusOf(approve),
      approved: `approved by ${named(approved)}`,
    },
    kernel: Object.fromEntries(PLACED.map((item) => [item.id, kernelView(told(item.id), item.id)])) as Record<StepId, KernelView>,
    audit: { counts: counts.join(", ") },
  };
}

/** What the story says at each step, in plain words. */
export function storyLines(facts: StoryFacts): Record<StepId, string> {
  const bed = (n: number) => amount(n, facts.bed.unit);
  return {
    intro: "Watch an agent babysit a 3D print.",
    ask: "A long print is running. You ask an agent to watch the print.",
    look: "The agent reads a webcam frame and sees a corner lifting.",
    warm: nb(`The agent warms the bed from ${bed(facts.bed.before)} to ${bed(facts.bed.after)}, under the ${facts.bed.max} limit.`),
    hot: nb(`The kernel refuses a ${facts.nozzle.value} nozzle, above your ${facts.nozzle.max} limit.`),
    loose: "Later, a webcam frame shows the print has come loose.",
    pause: "The agent pauses the print at once.",
    cancel: "Cancelling can't be undone, so the hub asks you first.",
    approve: `You approve the ${facts.approve.target}. The kernel rechecks, and the print is ${facts.printer.readings.find((reading) => reading.word)!.at.approve}.`,
    end: "Every command to every device takes this path.",
  };
}

/** The messages each step sends, in the message trace's shape, with numbers as a person reads them. */
export function storyTrace(facts: StoryFacts): Partial<Record<StepId, TraceLine[]>> {
  const out = (ask: Ask): TraceLine[] => [
    { kind: "note", text: ask.note },
    { kind: "request", method: ask.method, text: nb([ask.target, ask.value].filter(Boolean).join(" ")) },
  ];
  const answer = (text: string): TraceLine => ({ kind: "result", text, tone: TONES[text] ?? "ok" });
  const image: TraceLine = { kind: "result", text: facts.camera.image, tone: "ok" };
  const { refusal } = facts.nozzle;
  return {
    ask: [{ kind: "note", text: "nothing sent to the hub yet" }],
    look: [...out(facts.look), image],
    warm: [...out(facts.bed), answer(facts.bed.status)],
    hot: [...out(facts.nozzle), { kind: "error", code: refusal.code, name: refusal.name, reason: nb(refusal.reason) }],
    loose: [...out(facts.loose), image],
    pause: [...out(facts.pause), answer(facts.pause.status)],
    cancel: [...out(facts.cancel), answer(facts.cancel.status)],
    approve: [...out({ ...facts.approve, target: `${facts.approve.target} on ${facts.approve.device}` }), answer(facts.approve.status)],
    end: [{ kind: "note", text: facts.audit.counts }],
  };
}
