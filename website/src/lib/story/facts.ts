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
}

export type Tone = "ok" | "confirm" | "blocked";

/** The lifelines of the sequence diagram, left to right. */
export type Lifeline = "owner" | "agent" | "hub" | "printer";

export const LIFELINES: readonly Lifeline[] = ["owner", "agent", "hub", "printer"];

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
const verb = (exchange: Exchange): string => exchange.request.method.slice(exchange.request.method.lastIndexOf("/") + 1);

const TONES: Record<string, Tone> = { done: "ok", pending: "confirm", blocked: "blocked", failed: "blocked" };

/** Every word and number the landing story shows, from docs/demo/scenario.yaml and the printer's device file. */
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
  const viewAt = (id: StepId): Record<string, any> => {
    const own = told(id);
    if (own) return need(field(own, "printer"), `printer view after ${own.id}`);
    const next = PLACED.slice(PLACED.findIndex((item) => item.id === id))
      .map((item) => told(item.id))
      .find(Boolean);
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
  const audit = need(record.audit as Record<string, any> | undefined, "audit log");
  const counted = need(audit.counts as Record<string, number> | undefined, "audit counts");
  const logged = new Map<number, string>(need(audit.entries as Array<Record<string, any>> | undefined, "audit entries").map((entry) => [Number(entry.seq), String(entry.status)]));
  const lifeline = (principal: string): Lifeline => {
    if (principal === agent) return "agent";
    if (principal === person) return "owner";
    throw new Error(`docs/demo/scenario.yaml has a request from ${principal}, who has no lifeline in the landing story.`);
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

/** What the story says at each step, one sentence each, in the record's words. */
export function storyLines(facts: StoryFacts): Record<StepId, string> {
  const frame = facts.camera.channel;
  const state = facts.printer.readings.find((reading) => reading.word)!.at.approve;
  return {
    intro: "An agent watches a 3D print through the OpenHAL hub.",
    ask: `The ${facts.owner} starts a long print and asks an agent to watch the print.`,
    look: `When the agent reads a ${frame} from the printer's webcam, the ${frame} shows that ${facts.bed.note}.`,
    warm: nb(`Because a bed target of ${facts.bed.value} is inside the ${facts.owner}'s limit of ${facts.bed.max}, the hub forwards the agent's request to the printer.`),
    hot: nb(
      `Because a nozzle temperature of ${facts.nozzle.value} is above the ${facts.owner}'s limit of ${facts.nozzle.max} in ${facts.file}, the hub refuses the agent's request and returns ${facts.nozzle.refusal.name}.`,
    ),
    loose: `When the agent reads the webcam again later, the ${frame} shows that ${facts.pause.note}.`,
    pause: `Because pausing needs no confirmation in ${facts.file}, the hub forwards the agent's ${facts.pause.target} request to the printer at once.`,
    cancel: `Because ${facts.cancel.note}, the hub holds the agent's ${facts.cancel.target} request until a person approves or rejects the request.`,
    approve: `When ${facts.approve.note}, the hub sends the ${facts.approve.target} to the printer and the printer's state changes to ${state}.`,
    end: `Because every request passes through the hub, the audit log holds ${facts.audit.requests} requests, with ${facts.audit.refused} refused and ${facts.audit.confirmed} confirmed by a person.`,
  };
}
