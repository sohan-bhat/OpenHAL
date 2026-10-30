import { readDeviceFile, storyFacts, type DeviceFile, type StoryFacts, type Tone } from "./facts";
import { loadScenario, type Scenario } from "../scenario";

/**
 * The three captions, the owner's of 2026-10-29 with every verb made mechanical on 2026-10-30, so the
 * hub and the printer pass, block and hold requests and never act like people. A unit test checks
 * their numbers against the record.
 */
export const CAPTIONS = [
  "The agent sends a request to set the bed to 70 °C. Your limit is 110 °C, so the hub passes the request to the printer.",
  "The agent sends a request to set the nozzle to 300 °C. Your limit is 260 °C, so the hub blocks the request.",
  "The agent sends a request to cancel the print. A cancel can't be undone, so the hub holds the request for your approval.",
] as const;

/** The diagram's three columns, left to right, each with a lifeline. */
export type Column = "agent" | "hub" | "printer";

export const COLUMNS: readonly Column[] = ["agent", "hub", "printer"];

export const HEADS: Record<Column, string> = { agent: "Agent", hub: "OpenHAL hub", printer: "Printer" };

/** A stretch of one step, its start and its length, each as a share of the step. */
export type Span = readonly [number, number];

/** One stretch of a request's solid arrow, which the hub holds in amber when `held`. */
export interface Leg {
  from: Column;
  to: Column;
  held: boolean;
  draws: Span;
}

/** A request, its label over the first leg, and the person's approval when the label is Approve. */
export interface Request {
  kind: "request";
  label: string;
  approve: boolean;
  shows: Span;
  legs: Leg[];
}

/** A reply, a dashed arrow from where the request stopped back to the agent, with its answer word. */
export interface Reply {
  kind: "reply";
  from: Column;
  answer: string;
  tone: Tone;
  draws: Span;
}

export type Row = Request | Reply;

/** A value of the printer panel, and the value a step changes it to. */
export interface Reading {
  name: string;
  value: string;
  becomes?: { value: string; at: Span };
}

export interface HowStep {
  caption: string;
  rule: { text: string; shows: Span };
  rows: Row[];
  readings: Reading[];
}

/** How long an arrowhead takes to show once its line arrives, as a share of the step. */
export const TIP = 0.02;

const leg = (from: Column, to: Column, draws: Span, held = false): Leg => ({ from, to, held, draws });

/**
 * The three steps of How it works, from the recorded scenario and the printer's device file. Each
 * step tells one request on one diagram, Agent, OpenHAL hub and Printer, with the limit the hub
 * checks under the hub and the printer's nozzle, bed and state under the printer. A request the hub
 * passes reaches the printer and done returns to the agent, a blocked request stops at the hub with
 * LIMIT_EXCEEDED, and the hub holds the cancel as pending until the person approves.
 */
export function howSteps(facts: StoryFacts = storyFacts()): HowStep[] {
  const [nozzle, bed, state] = facts.printer.readings;
  const answer = (said: { answer?: { text: string; tone: Tone } }[]) => said[said.length - 1].answer!;
  const warmed = answer(facts.said.warm);
  const refused = answer(facts.said.hot);
  const held = answer(facts.said.cancel);
  const approved = answer(facts.said.approve);
  const panel = (bedNow: string, stateNow: string): Reading[] => [
    { name: "Nozzle", value: nozzle.at.warm },
    { name: "Bed", value: bedNow },
    { name: "State", value: stateNow },
  ];
  return [
    {
      caption: CAPTIONS[0],
      rule: { text: `Bed ≤ ${facts.bed.max}`, shows: [0.34, 0.06] },
      rows: [
        { kind: "request", label: facts.said.warm[0].label, approve: false, shows: [0.06, 0.06], legs: [leg("agent", "hub", [0.12, 0.22]), leg("hub", "printer", [0.42, 0.18])] },
        { kind: "reply", from: "printer", answer: warmed.text, tone: warmed.tone, draws: [0.66, 0.24] },
      ],
      readings: panel(bed.at.look, state.at.warm).map((reading) => (reading.name === "Bed" ? { ...reading, becomes: { value: bed.at.warm, at: [0.6, 0.05] } } : reading)),
    },
    {
      caption: CAPTIONS[1],
      rule: { text: `Nozzle ≤ ${facts.nozzle.max}`, shows: [0.36, 0.06] },
      rows: [
        { kind: "request", label: facts.said.hot[0].label, approve: false, shows: [0.06, 0.06], legs: [leg("agent", "hub", [0.12, 0.24])] },
        { kind: "reply", from: "hub", answer: refused.text, tone: refused.tone, draws: [0.46, 0.2] },
      ],
      readings: panel(bed.at.hot, state.at.hot),
    },
    {
      caption: CAPTIONS[2],
      rule: { text: `${facts.cancel.target[0].toUpperCase()}${facts.cancel.target.slice(1)} needs approval`, shows: [0.28, 0.05] },
      rows: [
        { kind: "request", label: facts.said.cancel[0].label, approve: false, shows: [0.05, 0.05], legs: [leg("agent", "hub", [0.1, 0.18], true)] },
        { kind: "reply", from: "hub", answer: held.text, tone: held.tone, draws: [0.34, 0.14] },
        { kind: "request", label: "Approve", approve: true, shows: [0.52, 0.05], legs: [leg("hub", "printer", [0.58, 0.14])] },
        { kind: "reply", from: "printer", answer: approved.text, tone: approved.tone, draws: [0.77, 0.15] },
      ],
      readings: panel(bed.at.hot, state.at.hot).map((reading) => (reading.name === "State" ? { ...reading, becomes: { value: state.at.approve, at: [0.72, 0.04] } } : reading)),
    },
  ];
}

/** The steps for a record and a device file, for tests that change either. */
export const howStepsFor = (scenario: Scenario = loadScenario(), file: DeviceFile = readDeviceFile()): HowStep[] => howSteps(storyFacts(scenario, file));

/** A span of one step as a span of the whole section's scroll, from 0 to 1. */
export const across = (index: number, count: number, [at, length]: Span): Span => [(index + at) / count, length / count];
