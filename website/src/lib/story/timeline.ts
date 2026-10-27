import { span, step, type StepId } from "./script";

export interface Run {
  at: number;
  d: number;
  out: number;
}

export type Lane = "send" | "look" | "read" | "blocked" | "pending" | "done";

export interface Fill extends Run {
  wire: 1 | 2 | 3 | 4;
  lane: Lane;
}

const reads: StepId[] = ["look", "loose"];
const commands: StepId[] = ["warm", "hot", "pause", ...span("cancel")];

/** Which steps show each piece of the scene, by station. A piece shows for the whole of each step it names. */
export const AGENT = {
  person: ["ask"] as StepId[],
  asks: {
    look: ["look"] as StepId[],
    bed: ["warm"] as StepId[],
    nozzle: ["hot"] as StepId[],
    loose: ["loose"] as StepId[],
    pause: ["pause"] as StepId[],
    cancel: span("cancel"),
  },
  hears: {
    look: ["look"] as StepId[],
    bed: ["warm"] as StepId[],
    nozzle: ["hot"] as StepId[],
    loose: ["loose"] as StepId[],
    pause: ["pause"] as StepId[],
    cancel: span("cancel"),
  },
};

export const HUB = {
  nozzle: ["hot"] as StepId[],
  bed: ["warm"] as StepId[],
  cancel: ["cancel", "wake"] as StepId[],
  asked: span("cancel"),
};

export const DRIVER = {
  moonraker: ["warm", "pause"] as StepId[],
  http: reads,
  bed: ["warm"] as StepId[],
  pause: ["pause"] as StepId[],
  waiting: ["intro", "ask", "look", "hot", "loose", ...span("cancel")] as StepId[],
};

export const PRINTER = {
  before: ["intro", "ask", "look"] as StepId[],
  after: span("warm"),
  printing: span("intro", "loose"),
  paused: span("pause"),
};

export const CAMERA = {
  lifting: span("intro", "hot"),
  loose: span("loose"),
  corner: span("look", "hot"),
  off: span("loose"),
};

export const WIRES = {
  read: reads,
  write: ["warm", "hot"] as StepId[],
  action: ["pause", ...span("cancel")] as StepId[],
  command: ["intro", "ask", ...commands] as StepId[],
};

const fill = (wire: Fill["wire"], lane: Lane, at: number, d: number, out: number): Fill => ({ wire, lane, at, d, out });

function trip(id: StepId, out: Lane, back: Lane, depth: number): Fill[] {
  const { from, to } = step(id);
  const wires = ([1, 2, 3, 4] as const).slice(0, depth);
  const leg = 3;
  const going = wires.map((wire, index) => fill(wire, out, from + 2 + index * leg, leg, to));
  const returning = [...wires].reverse().map((wire, index) => fill(wire, back, from + 4 + depth * leg + index * leg, leg, to));
  return [...going, ...returning];
}

/** Each step's message drawn out along the wires it travels and its answer drawn back. */
export const FILLS: Fill[] = [
  ...trip("look", "look", "read", 4),
  ...trip("warm", "send", "done", 4),
  ...trip("hot", "send", "blocked", 2),
  ...trip("loose", "look", "read", 4),
  ...trip("pause", "send", "done", 4),
  ...trip("cancel", "send", "pending", 2),
];
