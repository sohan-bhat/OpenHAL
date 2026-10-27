import { span, step, type Station, type StepId } from "./script";

export interface Run {
  at: number;
  d: number;
  out: number;
}

export type Lane = "send" | "look" | "read" | "blocked" | "pending" | "done";

export type WireId = 1 | 2 | 3 | 4;

export interface Fill extends Run {
  wire: WireId;
  lane: Lane;
}

export interface Trip {
  id: StepId;
  out: Lane;
  back: Lane;
  wires: WireId[];
}

const reads: StepId[] = ["look", "loose"];

/** Which steps show each piece of the scene, by station. A piece shows for the whole of each step it names. */
export const AGENT = {
  person: ["ask"] as StepId[],
  logged: ["end"] as StepId[],
  asks: {
    look: ["look"] as StepId[],
    bed: ["warm"] as StepId[],
    nozzle: ["hot"] as StepId[],
    loose: ["loose"] as StepId[],
    pause: ["pause"] as StepId[],
    cancel: ["cancel", "approve"] as StepId[],
  },
  hears: {
    look: ["look"] as StepId[],
    bed: ["warm"] as StepId[],
    nozzle: ["hot"] as StepId[],
    loose: ["loose"] as StepId[],
    pause: ["pause"] as StepId[],
    cancel: ["cancel", "approve"] as StepId[],
  },
};

export const HUB = {
  nozzle: ["hot"] as StepId[],
  bed: ["warm"] as StepId[],
  cancel: ["cancel", "approve"] as StepId[],
  asked: ["cancel", "approve"] as StepId[],
  pending: ["cancel"] as StepId[],
  approved: ["approve"] as StepId[],
};

export const DRIVER = {
  moonraker: ["warm", "pause", "approve"] as StepId[],
  http: reads,
  frame: reads,
  bed: ["warm"] as StepId[],
  pause: ["pause"] as StepId[],
  cancel: ["approve"] as StepId[],
  waiting: ["intro", "ask", "hot", "cancel", "end"] as StepId[],
};

export const CAMERA = {
  lifting: span("intro", "hot"),
  loose: span("loose"),
  corner: span("look", "hot"),
  off: span("loose"),
};

export const WIRES = {
  read: reads,
  command: ["intro", "ask", "warm", "hot", "pause", "cancel", "approve", "end"] as StepId[],
};

/** Each message's way through the scene. A read leaves the driver for the webcam, every command for the printer. */
export const TRIPS: Trip[] = [
  { id: "look", out: "look", back: "read", wires: [1, 2, 3, 4] },
  { id: "warm", out: "send", back: "done", wires: [1, 2, 3, 4] },
  { id: "hot", out: "send", back: "blocked", wires: [1, 2] },
  { id: "loose", out: "look", back: "read", wires: [1, 2, 3, 4] },
  { id: "pause", out: "send", back: "done", wires: [1, 2, 3, 4] },
  { id: "cancel", out: "send", back: "pending", wires: [1, 2] },
  { id: "approve", out: "send", back: "done", wires: [2, 3, 4] },
];

const ENDS: Record<WireId, [Station, Station]> = { 1: ["client", "hub"], 2: ["hub", "kernel"], 3: ["kernel", "driver"], 4: ["driver", "printer"] };

/** The stations a trip's message passes, which are the stations its step lights. */
export function stations(trip: Trip): Station[] {
  const reading = trip.out === "look";
  return [...new Set(trip.wires.flatMap((wire) => ENDS[wire].map((end): Station => (end === "printer" && reading ? "camera" : end))))];
}

const fill = (wire: WireId, lane: Lane, at: number, d: number, out: number): Fill => ({ wire, lane, at, d, out });

function fills({ id, out, back, wires }: Trip): Fill[] {
  const { from, to } = step(id);
  const leg = 3;
  const going = wires.map((wire, index) => fill(wire, out, from + 2 + index * leg, leg, to));
  const returning = [...wires].reverse().map((wire, index) => fill(wire, back, from + 4 + wires.length * leg + index * leg, leg, to));
  return [...going, ...returning];
}

/** Each step's message drawn out along the wires it travels and its answer drawn back. */
export const FILLS: Fill[] = TRIPS.flatMap(fills);
