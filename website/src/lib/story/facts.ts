import { readFileSync } from "node:fs";
import { join } from "node:path";
import { parse } from "yaml";
import { loadScenario, type Exchange, type Scenario } from "../scenario";
import { REPO_ROOT } from "../spec-meta.mjs";
import { reasonLines } from "../trace-html.mjs";
import { PLACED, type StepId } from "./script";

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

export interface Reading {
  name: string;
  word: boolean;
  at: Record<StepId, string>;
  /** What the hub read while the nozzle cooled after the approved action, before the last reading, which is the ending's. */
  cooling: string[];
  /** Whether the reading is a target the approved action leaves stale, since the action's effects in the device file do not list the channel. */
  stale: boolean;
}

export type Tone = "ok" | "confirm" | "blocked";

/**
 * The lifelines of the sequence diagram, left to right and evenly spaced, the owner's order of
 * 2026-10-27. The owner sits between the agent and the hub, so the owner's own arrows never cross
 * the agent's lifeline, and the agent's arrows pass over the owner's.
 */
export type Lifeline = "agent" | "owner" | "hub" | "printer";

export const LIFELINES: readonly Lifeline[] = ["agent", "owner", "hub", "printer"];

export interface Answer {
  text: string;
  tone: Tone;
}

/** One arrow of the sequence diagram, from the lifeline that sends it to the lifeline it reaches, with the answer at its end. */
export interface Said {
  from: Lifeline;
  to: Lifeline;
  label: string;
  answer?: Answer;
}

/** The steps that send something, every counted step but the ending. */
export type Sending = Exclude<StepId, "intro" | "end">;

/** What the owner asks the agent, the one message that is not a request to the hub. */
export const ASKED = "watch my print";

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

/** The exchange each step tells. The title, the ask and the ending send nothing to the hub. */
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
  agent: string;
  owner: string;
  printer: { id: string; name: string; driver: string; readings: Reading[] };
  camera: { id: string; channel: string; driver: string };
  file: string;
  confirmed: string;
  look: Ask;
  loose: Ask;
  bed: Ask & { channel: string; max: string; before: number; after: number; unit: string; status: string };
  nozzle: Ask & { channel: string; max: string; refusal: Refusal };
  pause: Ask & { status: string };
  cancel: Ask & { status: string };
  approve: Ask & { device: string; status: string; approved: string };
  said: Record<Sending, Said[]>;
  audit: { counts: string; requests: number; refused: number; confirmed: number };
}

export interface DeviceFile {
  device: string | { name: string };
  id: string;
  connect: Record<string, unknown>;
  read: Record<string, { unit?: string }>;
  write: Record<string, { unit?: string; min?: number; max?: number }>;
  actions: Record<string, { confirm?: string; effects?: string[] } | null>;
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

export function readDeviceFile(path = join(REPO_ROOT, "examples", "print-babysitter", "printer.hal.yaml")): DeviceFile {
  return parse(readFileSync(path, "utf8")) as DeviceFile;
}

function need<T>(found: T | undefined | null, what: string): T {
  if (found === undefined || found === null) throw new Error(`docs/demo/scenario.yaml has no ${what}, which the example's story and How it works show.`);
  return found;
}

const params = (exchange: Exchange): Record<string, any> => exchange.request.params ?? {};
const statusOf = (exchange: Exchange): string => String(exchange.result?.status ?? "");
const field = (exchange: Exchange, key: string): any => (exchange as Record<string, any>)[key];
const verb = (exchange: Exchange): string => exchange.request.method.slice(exchange.request.method.lastIndexOf("/") + 1);

const TONES: Record<string, Tone> = { done: "ok", pending: "confirm", blocked: "blocked", failed: "blocked" };

/** Every word and number the example's story and How it works show, from docs/demo/scenario.yaml and the printer's device file. */
export function storyFacts(scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): StoryFacts {
  const record = scenario.record as Scenario["record"] & Record<string, any>;
  const exchanges = record.exchanges;
  const described = (id: string) => need(record.devices?.find((item) => item.id === id), `description of ${id}`);
  const byId = (id: string) => need(exchanges.find((exchange) => exchange.id === id), `exchange ${id}`);
  const told = (id: StepId) => (TOLD[id] ? byId(IDS[TOLD[id]!]) : undefined);
  const look = byId(IDS.look);
  const loose = byId(IDS.loose);
  const bed = byId(IDS.bed);
  const nozzle = byId(IDS.nozzle);
  const pause = byId(IDS.pause);
  const cancel = byId(IDS.cancel);
  const approve = byId(IDS.approve);
  const principals = need(record.principals as Record<string, string> | undefined, "principals");
  const agent = need(principals.agent, "agent principal");
  const person = need(principals.person, "person principal");
  const bedChannel = String(params(bed).channel);
  const nozzleChannel = String(params(nozzle).channel);
  const limit = (channel: string) => amount(file.write[channel]?.max, file.write[channel]?.unit);
  const change = need(field(bed, bedChannel), `${bedChannel} before and after`);
  const printer = described(String(params(bed).device));
  const webcam = described(String(params(look).device));
  const error = need(nozzle.error, `error for ${IDS.nozzle}`);
  const name = typeof file.device === "string" ? file.device : file.device.name;
  const note = (exchange: Exchange) => String(need(exchange.before, `narration for ${exchange.id}`));
  const write = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).channel), value: amount(params(exchange).value, params(exchange).unit), note: note(exchange) });
  const act = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: String(params(exchange).action), value: "", note: note(exchange) });
  const read = (exchange: Exchange): Ask => ({ method: exchange.request.method, target: `${params(exchange).device} ${params(exchange).channel}`, value: "", note: note(exchange) });
  const viewed = exchanges.filter((exchange) => field(exchange, "printer"));
  const cooled = ((field(approve, "cooling") ?? []) as Array<Record<string, any>>).map((entry) => need(entry.printer as Record<string, any> | undefined, `printer view while ${IDS.approve} cools`));
  const viewAt = (id: StepId): Record<string, any> => {
    const own = told(id);
    if (own) return need(field(own, "printer"), `printer view after ${own.id}`);
    const next = PLACED.slice(PLACED.findIndex((item) => item.id === id))
      .map((item) => told(item.id))
      .find(Boolean);
    return (next ? field(next, "printer") : cooled[cooled.length - 1]) ?? field(viewed[viewed.length - 1], "printer") ?? {};
  };
  const readingAt = (what: string, pick: (view: Record<string, any>) => string | undefined): Record<StepId, string> =>
    Object.fromEntries(PLACED.map((item) => [item.id, need(pick(viewAt(item.id)), `${what} for the story's ${item.id} step`)])) as Record<StepId, string>;
  const quantity = (key: string) => (view: Record<string, any>) => (view[key] ? amount(Math.round(Number(view[key].value)), view[key].unit) : undefined);
  const effects = new Set(file.actions[String(approve.result?.target ?? "").slice(String(approve.result?.target ?? "").indexOf(":") + 1)]?.effects ?? []);
  const reading = (name: string, word: boolean, what: string, pick: (view: Record<string, any>) => string | undefined, channel?: string): Reading => ({
    name,
    word,
    at: readingAt(what, pick),
    cooling: cooled.slice(0, -1).map((view) => need(pick(view), `${what} while the nozzle cools`)),
    stale: channel !== undefined && channel in file.write && !effects.has(channel),
  });
  const readings: Reading[] = [
    reading("Nozzle", false, "the nozzle temperature", quantity("extruder_temp"), "extruder_temp"),
    reading("Bed target", false, "the bed target", quantity(bedChannel), bedChannel),
    reading("State", true, "the printer state", (view) => view.state, "state"),
  ];
  const audit = need(record.audit as Record<string, any> | undefined, "audit log");
  const counted = need(audit.counts as Record<string, number> | undefined, "audit counts");
  const logged = new Map<number, string>(need(audit.entries as Array<Record<string, any>> | undefined, "audit entries").map((entry) => [Number(entry.seq), String(entry.status)]));
  const lifeline = (principal: string): Lifeline => {
    if (principal === agent) return "agent";
    if (principal === person) return "owner";
    throw new Error(`docs/demo/scenario.yaml has a request from ${principal}, who has no lifeline in the example's story.`);
  };
  const answer = (exchange: Exchange): Answer => {
    if (exchange.error) return { text: String(exchange.error.data.name), tone: "blocked" };
    const status = statusOf(exchange) || need(logged.get(Number(field(exchange, "kernel")?.logged?.[0])), `audit status of ${exchange.id}`);
    return { text: status, tone: need(TONES[status], `a tone for the status ${status}`) };
  };
  const label = (exchange: Exchange): string => {
    const asked = params(exchange);
    if (asked.channel !== undefined && asked.value !== undefined) return nb(`${asked.channel} ${amount(asked.value, asked.unit)}`);
    if (asked.action !== undefined) return String(asked.action);
    return [verb(exchange), asked.channel].filter(Boolean).join(" ");
  };
  const said = (exchange: Exchange): Said[] => {
    const from = lifeline(String(exchange.by));
    const reply = answer(exchange);
    const stops = Boolean(exchange.error) || reply.text === "pending";
    const target = String(exchange.result?.target ?? "");
    if (!target) return [{ from, to: stops ? "hub" : "printer", label: label(exchange), answer: reply }];
    return [
      { from, to: "hub", label: verb(exchange) },
      { from: "hub", to: stops ? "hub" : "printer", label: target.slice(target.indexOf(":") + 1), answer: reply },
    ];
  };
  const sending = Object.fromEntries(
    PLACED.filter((item) => TOLD[item.id]).map((item) => [item.id, said(told(item.id)!)]),
  ) as Record<Exclude<Sending, "ask">, Said[]>;
  const approvedTarget = String(need(approve.result?.target, `target of ${IDS.approve}`));
  const approvedBy = String(need(field(approve, "kernel")?.approved_by, `approver of ${IDS.approve}`));
  return {
    agent,
    owner: named(person),
    printer: { id: printer.id, name, driver: printer.driver, readings },
    camera: { id: webcam.id, channel: String(params(look).channel), driver: webcam.driver },
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
    cancel: { ...act(cancel), status: statusOf(cancel) },
    approve: {
      method: approve.request.method,
      target: approvedTarget.slice(approvedTarget.indexOf(":") + 1),
      device: String(approve.result?.device),
      value: "",
      note: note(approve),
      status: statusOf(approve),
      approved: `approved by ${named(approvedBy)}`,
    },
    said: { ask: [{ from: "owner", to: "agent", label: ASKED }], ...sending },
    audit: {
      counts: Object.entries(counted)
        .map(([key, count]) => `${count} ${key.replaceAll("_", " ")}`)
        .join(", "),
      requests: need(counted.requests, "count of requests"),
      refused: need(counted.refused, "count of refusals"),
      confirmed: need(counted.confirmed_by_a_person, "count of requests a person confirmed"),
    },
  };
}

/**
 * What the story says at each step, the owner's nine captions from 2026-10-27, with every value
 * from the record and the device file. Each caption reads on its own screen, in at most two
 * sentences, and addresses the person who owns the printer.
 */
export function storyLines(facts: StoryFacts): Record<StepId, string> {
  return {
    intro: "An agent watches a 3D print through the OpenHAL hub.",
    ask: "You start a long print and ask an agent to watch it.",
    look: "The agent checks the webcam and sees a corner of the first layer lifting.",
    warm: nb(`The agent sends a request to set the bed to ${facts.bed.value}. Your limit is ${facts.bed.max}, so the hub passes the request to the printer.`),
    hot: nb(`The agent also sends a request for a nozzle temperature of ${facts.nozzle.value} to help the print stick. Your limit is ${facts.nozzle.max}, so the hub blocks the request.`),
    loose: "Later, the webcam shows the print has come loose.",
    pause: "The agent pauses the print. Pausing is safe, so no one has to approve it.",
    cancel: "Cancelling can't be undone, so the hub holds the request until you approve it.",
    approve: `You approve, and the hub sends the ${facts.approve.target} to the printer.`,
    end: `The audit log records all ${facts.audit.requests} requests, including the blocked request and your approval.`,
  };
}
