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

export type Lane = "send" | "blocked" | "reading" | "done";

export interface Fill extends Run {
  wire: 1 | 2 | 3 | 4;
  lane: Lane;
}

const span = (arrive: number, out = NEVER): Span => ({ at: arrive, out });

const ask = at("ask", -8);
const retry = from("hold", 2);
const last = from("water", 2);

/** When each piece of the scene changes, by station. Every number is a point on the shot list. */
export const CLIENT = {
  request: span(ask),
  asked: span(ask, retry),
  retried: span(retry),
  limit: span(at("reply", -3), retry),
  interlock: span(at("hold", 14), last),
  done: span(at("done", -4)),
};

export const HUB = {
  duration: span(from("check", 22), at("reply", 4)),
  tank: span(from("hold", 16), from("refill", 2)),
};

const steps = (start: number, count: number, gap: number) => Array.from({ length: count }, (_, index) => start + index * gap);
const once = steps(at("check", 2), 2, 4);
const twice = steps(at("hold", 2), 4, 3);
const thrice = steps(at("water", 0), 5, 2.5);

export const KERNEL = {
  first: { units: span(once[0], retry), range: span(once[1], retry), verdict: span(once[1] + 4, retry) },
  second: {
    units: span(twice[0], last),
    range: span(twice[1], last),
    rate: span(twice[2], last),
    interlocks: span(twice[3], last),
    verdict: span(twice[3] + 3, last),
  },
  third: {
    units: span(thrice[0]),
    range: span(thrice[1]),
    rate: span(thrice[2]),
    interlocks: span(thrice[3]),
    confirmation: span(thrice[4]),
    verdict: span(thrice[4] + 3),
  },
};

const grant = at("water", 14);

export const DRIVER = {
  waiting: span(ALWAYS, grant),
  granted: span(grant),
  sent: span(grant + 8),
};

const empty = at("dry", 2);
const refilled = at("refill", 2);
const held = at("hold", 12);
const pumping = at("water", 30);
const stopped = at("soil", 30);

export const DEVICE = {
  tank: { ok: span(ALWAYS, empty), empty: span(empty, refilled), refilled: span(refilled) },
  pump: {
    off: span(ALWAYS, held),
    held: span(held, refilled),
    ready: span(refilled, pumping),
    on: span(pumping, stopped),
    done: span(stopped),
  },
  soil: { at: at("soil", 2), d: 26, out: NEVER } as Run,
};

const fill = (wire: Fill["wire"], lane: Lane, arrive: number, d: number, out = NEVER): Fill => ({ wire, lane, at: arrive, d, out });

export const FILLS: Fill[] = [
  fill(1, "send", from("check", 4), 10, at("reply", 4)),
  fill(2, "send", from("check", 14), 10, at("reply", 4)),
  fill(2, "blocked", from("reply", 2), 10, from("dry", 4)),
  fill(1, "blocked", from("reply", 12), 10, from("dry", 4)),
  fill(1, "send", retry, 8, from("refill", 2)),
  fill(2, "send", retry + 8, 8, from("refill", 2)),
  fill(4, "reading", from("hold", 14), 6, from("refill", 2)),
  fill(3, "reading", from("hold", 20), 6, from("refill", 2)),
  fill(2, "blocked", held, 8, from("water")),
  fill(1, "blocked", held + 8, 8, from("water")),
  fill(1, "send", last, 8),
  fill(2, "send", last + 8, 8),
  fill(3, "send", grant, 8),
  fill(4, "send", grant + 8, 8),
  fill(4, "done", from("done", 2), 7),
  fill(3, "done", from("done", 9), 7),
  fill(2, "done", from("done", 16), 7),
  fill(1, "done", from("done", 23), 7),
];

/** When each line over the stage arrives. Each one leaves as the next arrives. */
export const NOTE_AT: Record<Exclude<ShotId, "wide">, number> = {
  ask: from("ask", 11),
  check: at("check", 6),
  reply: at("reply", -4),
  dry: at("dry", 0),
  hold: at("hold", 8),
  refill: at("refill", 0),
  water: at("water", 8),
  soil: at("soil", 0),
  done: at("done", -4),
  end: from("end", 12),
};

export const TITLE_OUT = from("ask", 4);

/** The moment each step of the static list shows its station at, once its shot has played out. */
export const SNAP_AT: Record<Exclude<ShotId, "wide" | "end">, number> = {
  ask: at("ask", 20),
  check: at("check", 32),
  reply: at("reply", 20),
  dry: at("dry", 18),
  hold: at("hold", 32),
  refill: at("refill", 18),
  water: at("water", 32),
  soil: at("soil", 32),
  done: at("done", 20),
};
