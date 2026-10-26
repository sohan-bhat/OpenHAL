import { ALWAYS, NEVER, at, from, type ShotId } from "./script";

export interface Span {
  at: number;
  out: number;
}

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

export type Word = "ok" | "blocked" | "not needed" | "required";

export interface Check {
  span: Span;
  word: Word;
}

export interface Pass {
  checks: Check[];
  verdict: Span;
}

const span = (arrive: number, out = NEVER): Span => ({ at: arrive, out });

const look = at("watch", -6);
const bed = at("warm", -4);
const nozzle = at("hot", -4);
const second = from("loose", 2);
const pause = from("pause", 2);
const cancel = at("cancel", -4);

/** When each piece of the scene changes, by station. Every number is a point on the shot list. */
export const CLIENT = {
  asks: [span(look, bed), span(bed, nozzle), span(nozzle, second), span(second, pause), span(pause, cancel), span(cancel)],
  hears: [
    span(from("look", 50), bed),
    span(from("heat", 36), nozzle),
    span(at("hot", 32), second),
    span(at("loose", 24), pause),
    span(at("pause", 44), cancel),
    span(from("wake", 4)),
  ],
};

export const HUB = {
  bed: span(at("warm", 4), from("heat")),
  nozzle: span(at("hot", 8), from("reply", 18)),
  cancel: span(at("cancel", 4)),
  asked: span(at("cancel", 26)),
};

const steps = (start: number, words: Word[], gap: number, out: number): Pass => {
  const checks = words.map((word, index) => ({ word, span: span(start + index * gap, out) }));
  return { checks, verdict: span(checks[checks.length - 1].span.at + 3, out) };
};

export const KERNEL = {
  bed: steps(at("warm", 14), ["ok", "ok", "ok", "ok", "not needed"], 3, nozzle),
  nozzle: steps(at("hot", 12), ["ok", "blocked"], 3, pause),
  pause: steps(at("pause", 0), ["ok", "ok", "ok", "ok", "not needed"], 2.5, cancel),
  cancel: steps(at("cancel", 12), ["ok", "ok", "ok", "ok", "required"], 2.5, NEVER),
};

const granted = from("heat", 10);
const paused = at("pause", 20);

export const DRIVER = {
  waiting: [span(ALWAYS, granted), span(granted + 24, paused), span(paused + 24)],
  bed: span(granted, granted + 24),
  pause: span(paused, paused + 24),
  sent: [span(granted + 6, granted + 24), span(paused + 4, paused + 24)],
  moonraker: [span(granted, granted + 24), span(paused, paused + 24)],
  http: [span(from("look", 20), from("look", 38)), span(from("loose", 20), at("loose", 12))],
};

export const PRINTER = {
  printing: span(ALWAYS, paused + 8),
  paused: span(paused + 8),
  bed: { at: at("heat", 0), d: 22, out: NEVER } as Run,
};

const swapped = at("loose", -2);

export const CAMERA = {
  lifting: span(ALWAYS, swapped),
  loose: span(swapped),
  corner: span(at("look", 4), swapped - 2),
  off: span(at("loose", 6)),
};

const fill = (wire: Fill["wire"], lane: Lane, arrive: number, d: number, out = NEVER): Fill => ({ wire, lane, at: arrive, d, out });
const sent = granted + 4;
const back = (lane: Lane, start: number, out: number): Fill[] => [4, 3, 2, 1].map((wire, index) => fill(wire as Fill["wire"], lane, start + index * 4, 4, out));
const done = (start: number, out: number): Fill[] => back("done", start, out);
const read = (start: number, out: number): Fill[] => [1, 2, 3, 4].map((wire, index) => fill(wire as Fill["wire"], "look", start + index * 6, 6, out));

export const FILLS: Fill[] = [
  ...read(from("look", 2), bed),
  ...back("read", from("look", 34), bed),
  fill(1, "send", at("warm", 0), 6, nozzle),
  fill(2, "send", at("warm", 6), 6, nozzle),
  fill(3, "send", granted - 6, 6, nozzle),
  fill(4, "send", sent, 6, nozzle),
  ...done(sent + 6, nozzle),
  fill(1, "send", at("hot", 0), 6, second),
  fill(2, "send", at("hot", 6), 6, second),
  fill(2, "blocked", KERNEL.nozzle.verdict.at + 2, 6, second),
  fill(1, "blocked", KERNEL.nozzle.verdict.at + 8, 6, second),
  ...read(second + 2, pause),
  ...back("read", at("loose", 8), pause + 8),
  fill(1, "send", pause + 2, 6, cancel),
  fill(2, "send", pause + 8, 6, cancel),
  fill(3, "send", paused - 6, 6, cancel),
  fill(4, "send", paused + 2, 6, cancel),
  ...done(paused + 8, cancel),
  fill(1, "send", at("cancel", 0), 6),
  fill(2, "send", at("cancel", 6), 6),
  fill(2, "pending", KERNEL.cancel.verdict.at + 3, 6),
  fill(1, "pending", KERNEL.cancel.verdict.at + 9, 6),
];

/** When each line over the stage arrives. Each one leaves as the next arrives. */
export const NOTE_AT: Record<Exclude<ShotId, "wide">, number> = {
  watch: from("watch", 11),
  look: at("look", 0),
  warm: at("warm", -4),
  heat: at("heat", -6),
  hot: at("hot", -4),
  reply: from("reply", 0),
  loose: at("loose", 0),
  pause: from("pause", 4),
  cancel: at("cancel", -4),
  wake: at("wake", -2),
  end: from("end", 12),
};

export const TITLE_OUT = from("watch", 4);

/** The moment each step of the static list shows its station at, once its shot has played out. */
export const SNAP_AT: Record<Exclude<ShotId, "wide" | "end">, number> = {
  watch: at("watch", 20),
  look: at("look", 22),
  warm: at("warm", 34),
  heat: at("heat", 28),
  hot: at("hot", 32),
  reply: at("reply", 16),
  loose: at("loose", 22),
  pause: at("pause", 34),
  cancel: at("cancel", 34),
  wake: at("wake", 26),
};
