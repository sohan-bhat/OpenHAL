import { LIFELINES, type Answer, type Lifeline, type Sending, type StoryFacts } from "./facts";
import { NEVER, PLACED, step, type Span, type StepId } from "./script";

/** One stretch of an arrow between two lifelines, drawn from story time `at` over `d`, whose head lands at `lands`. */
export interface Leg {
  from: Lifeline;
  to: Lifeline;
  at: number;
  d: number;
  lands: number;
}

/** An arrow's words over the lifelines it spans, its label from `shows` and its answer from `answers`. */
export interface Words {
  from: Lifeline;
  to: Lifeline;
  label: string;
  mono: boolean;
  shows: number;
  answer?: Answer;
  answers: number;
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
  live: Span;
  held?: Span;
  lands: number;
}

/** When a row's arrow draws in the accent, which ends when the hub starts to hold it. */
export const drawing = (item: Row): Span => [item.live[0], item.held ? item.held[0] : item.live[1]];

export interface Sequence {
  heads: Record<Lifeline, string>;
  rows: Row[];
  readings: Array<{ name: string; word: boolean; values: Array<{ text: string; spans: Span[] }> }>;
  frames: { lifting: Span[]; loose: Span[] };
  seen: { lifting: Span[]; loose: Span[] };
}

/** Story time, from the start of a step, at which its label shows and its first leg starts to draw. */
export const SHOWS = 2;
const DRAWS = 4;
/** Story time a leg takes to cross one gap between lifelines, plus a fixed part. */
const PER_GAP = 5;
const BASE = 8;
/** Story time a request rests at the hub's lifeline before the hub forwards it. */
const RESTS = 4;
/** Story time from an arrowhead landing to its answer showing. */
const ANSWERS = 1;

const gaps = (from: Lifeline, to: Lifeline) => Math.abs(LIFELINES.indexOf(to) - LIFELINES.indexOf(from));
const capital = (word: string) => `${word[0].toUpperCase()}${word.slice(1)}`;

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
  const legs: Leg[] = [];
  const words: Words[] = [];
  let t = start + DRAWS;
  for (const [index, said] of facts.said[id].entries()) {
    const shows = index === 0 ? start + SHOWS : legs[legs.length - 1].lands + ANSWERS;
    const first = legs.length;
    for (const [from, to] of route(said.from, said.to)) {
      if (legs.length > first) t += RESTS;
      const d = BASE + PER_GAP * gaps(from, to);
      legs.push({ from, to, at: t, d, lands: t + d });
      t += d;
    }
    t += RESTS;
    words.push({ from: said.from, to: said.to, label: said.label, mono: id !== "ask", shows, answer: said.answer, answers: legs[legs.length - 1].lands + ANSWERS });
  }
  return { id, legs, words, live: [start + SHOWS, end], lands: legs[legs.length - 1].lands };
}

/** Whether the hub holds a row's request at its lifeline, which its amber answer says. */
const holds = (item: Pick<Row, "words">) => item.words[item.words.length - 1].answer?.tone === "confirm";

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
 * row's label shows, its arrow draws along the lifelines, and its answer shows once the last
 * arrowhead lands. A held request waits at the hub's lifeline until a later row from the owner
 * lands there. The printer's readings and the webcam's frame change when the request that changed
 * them lands.
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
  const readings = facts.printer.readings.map((reading) => ({
    name: reading.name,
    word: reading.word,
    values: runs(PLACED.map((item) => [item.index === 0 ? 0 : changes(item.id), reading.at[item.id]])),
  }));
  const read = (id: StepId) => rows.find((item) => item.id === id)!;
  const look = read("look");
  const loose = read("loose");
  return {
    heads: { owner: capital(facts.owner), agent: capital(facts.agent.slice(0, facts.agent.indexOf(":"))), hub: "OpenHAL hub", printer: capital(facts.printer.id) },
    rows,
    readings,
    frames: { lifting: [[0, loose.lands + ANSWERS]], loose: [[loose.lands + ANSWERS, NEVER]] },
    seen: { lifting: [[look.lands + ANSWERS, step("look").to]], loose: [[loose.lands + ANSWERS, step("loose").to]] },
  };
}
