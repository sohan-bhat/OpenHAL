import { LIFELINES, type Answer, type Lifeline, type Sending, type StoryFacts } from "./facts";
import { NEVER, PLACED, step, type Span, type StepId } from "./script";

/**
 * One stretch of an arrow between two lifelines, drawn from story time `at` over `d`, whose head
 * lands at `lands`. An arrow to a lifeline further left draws right to left. `over` is where the
 * owner's lifeline crosses the leg, as a share of the leg's width from its left end, when the leg
 * passes over the owner's lifeline on its way.
 */
export interface Leg {
  from: Lifeline;
  to: Lifeline;
  at: number;
  d: number;
  lands: number;
  back: boolean;
  over?: number;
}

/** An arrow's words over the lifelines it spans, its label from `shows`. */
export interface Words {
  from: Lifeline;
  to: Lifeline;
  label: string;
  mono: boolean;
  shows: number;
}

/**
 * The answer to a row's request, a dashed arrow from the lifeline the request reached back to the
 * lifeline that sent the request. The answer word shows at the arrow's start from `shows`, and the
 * arrow draws back over `leg`.
 */
export interface Reply {
  from: Lifeline;
  to: Lifeline;
  answer: Answer;
  shows: number;
  leg: Leg;
}

/**
 * One row of the sequence diagram, the message one step sends. The row is live while its step is
 * told, and a row the hub holds waits at the hub's lifeline from the moment it lands until the
 * request that releases it lands.
 */
export interface Row {
  id: Sending;
  legs: Leg[];
  words: Words[];
  reply?: Reply;
  live: Span;
  held?: Span;
  lands: number;
}

/** When a row's arrow draws in the accent, which ends when the hub starts to hold it. */
export const drawing = (item: Row): Span => [item.live[0], item.held ? item.held[0] : item.live[1]];

/** What the agent saw in each frame, the owner's words of 2026-10-27, shown under the webcam's drawing. */
export const SEEN = { lifting: "Seen: first layer corner lifting", loose: "Seen: print loose" } as const;

export type FrameName = "printing" | "lifting" | "loose";

export interface Sequence {
  heads: Record<Lifeline, string>;
  rows: Row[];
  readings: Array<{ name: string; word: boolean; values: Array<{ text: string; spans: Span[] }>; shown?: Span[] }>;
  frames: Record<FrameName, Span[]>;
  seen: { lifting: Span[]; loose: Span[] };
  notes: { lifting: Span[]; loose: Span[] };
}

/** Story time, from the start of a step, at which its label shows and its first leg starts to draw. */
export const SHOWS = 2;
const DRAWS = 4;
/** Story time a leg takes to cross one gap between lifelines, plus a fixed part. */
const PER_GAP = 3;
const BASE = 5;
/** Story time a request rests at the hub's lifeline before the hub forwards it. */
const RESTS = 3;
/** Story time from an arrowhead landing to its answer showing. */
const ANSWERS = 1;
/** Story time between two readings while the nozzle cools. */
const COOLS = 4;

const place = (name: Lifeline) => LIFELINES.indexOf(name);
const gaps = (from: Lifeline, to: Lifeline) => Math.abs(place(to) - place(from));
const capital = (word: string) => `${word[0].toUpperCase()}${word.slice(1)}`;

/** A leg from one lifeline to another, and where it passes over the owner's lifeline. */
function leg(from: Lifeline, to: Lifeline, at: number): Leg {
  const d = BASE + PER_GAP * gaps(from, to);
  const [left, right] = [Math.min(place(from), place(to)), Math.max(place(from), place(to))];
  const owner = place("owner");
  const over = owner > left && owner < right ? Math.round(((owner - left) / (right - left)) * 1000) / 1000 : undefined;
  return { from, to, at, d, lands: at + d, back: place(to) < place(from), ...(over === undefined ? {} : { over }) };
}

/** Every leg a message travels. A request for the printer stops at the hub's lifeline on the way. */
function route(from: Lifeline, to: Lifeline): Array<[Lifeline, Lifeline]> {
  if (from === to) return [];
  if (to === "printer" && from !== "hub") return [
    [from, "hub"],
    ["hub", "printer"],
  ];
  return [[from, to]];
}

function row(id: Sending, facts: StoryFacts): Row {
  const { from: start, to: end } = step(id);
  const said = facts.said[id];
  const legs: Leg[] = [];
  const words: Words[] = [];
  let t = start + DRAWS;
  for (const [index, item] of said.entries()) {
    const shows = index === 0 ? start + SHOWS : legs[legs.length - 1].lands + ANSWERS;
    const first = legs.length;
    for (const [from, to] of route(item.from, item.to)) {
      if (legs.length > first) t += RESTS;
      legs.push(leg(from, to, t));
      t = legs[legs.length - 1].lands;
    }
    t += RESTS;
    words.push({ from: item.from, to: item.to, label: item.label, mono: id !== "ask", shows });
  }
  const lands = legs[legs.length - 1].lands;
  const answer = said[said.length - 1].answer;
  const reached = legs[legs.length - 1].to;
  const sender = said[0].from;
  const reply = answer && reached !== sender ? { from: reached, to: sender, answer, shows: lands + ANSWERS, leg: leg(reached, sender, lands + ANSWERS) } : undefined;
  return { id, legs, words, ...(reply ? { reply } : {}), live: [start + SHOWS, end], lands };
}

/** Whether the hub holds a row's request at its lifeline, which its amber answer says. */
const holds = (item: Pick<Row, "reply">) => item.reply?.answer.tone === "confirm";

/** The changes of one value over the story, as the spans each text shows in. */
function runs(changes: Array<[number, string]>): Array<{ text: string; spans: Span[] }> {
  const out: Array<{ text: string; spans: Span[] }> = [];
  const kept = changes.filter(([, text], index) => index === 0 || text !== changes[index - 1][1]);
  kept.forEach(([at, text], index) => {
    const span: Span = [at, index + 1 < kept.length ? kept[index + 1][0] : NEVER];
    const found = out.find((entry) => entry.text === text);
    if (found) found.spans.push(span);
    else out.push({ text, spans: [span] });
  });
  return out;
}

/**
 * The sequence diagram the story draws, from the facts. Each step after the title adds one row. A
 * row's label shows, its arrow draws along the lifelines, and once the last arrowhead lands the
 * answer shows and a dashed reply draws back to the sender. A held request waits at the hub's
 * lifeline until a later row from the owner lands there. The printer's readings and the webcam's
 * frame change when the request that changed them lands, and before the agent first reads the
 * webcam the drawing shows the print as it started. Once the approved cancel lands, the nozzle
 * cools through the record's readings, and a target the cancel leaves stale leaves the panel.
 */
export function storySequence(facts: StoryFacts): Sequence {
  const rows = PLACED.filter((item) => item.id in facts.said).map((item) => row(item.id as Sending, facts));
  for (const [index, item] of rows.entries()) {
    if (!holds(item)) continue;
    const release = rows.slice(index + 1).find((later) => later.legs[0].from === "owner");
    item.held = [item.lands, release ? release.legs[0].lands : NEVER];
  }
  const changes = (id: StepId) => {
    const own = rows.find((item) => item.id === id);
    return own ? own.lands + ANSWERS : step(id).from;
  };
  const read = (id: StepId) => rows.find((item) => item.id === id)!;
  const approve = read("approve");
  const ran = approve.lands + ANSWERS;
  const cools = approve.reply ? approve.reply.leg.lands + ANSWERS : ran;
  const readings = facts.printer.readings.map((reading) => {
    const steps: Array<[number, string]> = PLACED.map((item) => [item.index === 0 ? 0 : changes(item.id), reading.at[item.id]]);
    const later = steps.findIndex(([at]) => at > cools);
    steps.splice(later < 0 ? steps.length : later, 0, ...reading.cooling.map((text, index): [number, string] => [cools + index * COOLS, text]));
    return { name: reading.name, word: reading.word, values: runs(steps), ...(reading.stale ? { shown: [[0, ran]] as Span[] } : {}) };
  });
  const looked = read("look").lands + ANSWERS;
  const loosened = read("loose").lands + ANSWERS;
  return {
    heads: { agent: capital(facts.agent.slice(0, facts.agent.indexOf(":"))), owner: capital(facts.owner), hub: "OpenHAL hub", printer: capital(facts.printer.id) },
    rows,
    readings,
    frames: { printing: [[0, looked]], lifting: [[looked, loosened]], loose: [[loosened, NEVER]] },
    seen: { lifting: [[looked, step("look").to]], loose: [[loosened, step("loose").to]] },
    notes: { lifting: [[looked, loosened]], loose: [[loosened, NEVER]] },
  };
}
