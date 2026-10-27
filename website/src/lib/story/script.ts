/**
 * The landing story as a list of steps, measured in vh of scroll. A point in the story is its story
 * time, from 0 at the title to TOTAL at the end. Each piece of the scene shows during spans of
 * story time, so a caption and the arrow it describes change together, and scrolling back plays
 * the story in reverse.
 */

export type StepId = "intro" | "ask" | "look" | "warm" | "hot" | "loose" | "pause" | "cancel" | "approve" | "end";

export interface Step {
  id: StepId;
  length: number;
}

/**
 * Screens tall enough that the stage may play. The height is under the shortest stage of any
 * layout with the header, so the story never turns off while a phone hides its toolbars.
 * Story.astro and the runtime still check the fit, the whole stage first and then the short one.
 */
export const CAMERA = "(prefers-reduced-motion: no-preference) and (min-height: 600px)";

export const STEPS: readonly Step[] = [
  { id: "intro", length: 20 },
  { id: "ask", length: 44 },
  { id: "look", length: 50 },
  { id: "warm", length: 50 },
  { id: "hot", length: 50 },
  { id: "loose", length: 50 },
  { id: "pause", length: 50 },
  { id: "cancel", length: 50 },
  { id: "approve", length: 50 },
  { id: "end", length: 40 },
];

export interface Placed extends Step {
  index: number;
  from: number;
  to: number;
}

export const PLACED: readonly Placed[] = (() => {
  let t = 0;
  return STEPS.map((item, index) => ({ ...item, index, from: t, to: (t += item.length) }));
})();

export const TOTAL = PLACED[PLACED.length - 1].to;

/** The steps a visitor counts, every one after the title. */
export const COUNTED: readonly Placed[] = PLACED.filter((item) => item.id !== "intro");

export function step(id: StepId): Placed {
  const found = PLACED.find((item) => item.id === id);
  if (!found) throw new Error(`No step ${id}`);
  return found;
}

/** The index of the step that holds story time t. */
export function stepAt(t: number): number {
  const found = PLACED.findIndex((item) => t < item.to);
  return found < 0 ? PLACED.length - 1 : found;
}

/** Later than any story time, for a piece that stays once it shows. */
export const NEVER = 100000;

/** A stretch of story time, from its first moment up to, but not including, its last. */
export type Span = readonly [number, number];

/** The span a step holds. The last step holds on past the end of the runway. */
export function held(id: StepId): Span {
  const { from, to } = step(id);
  return [from, to === TOTAL ? NEVER : to];
}

const round = (n: number) => Math.round(n * 100) / 100;

/** Whether story time t falls inside one of the spans. */
export const inside = (spans: readonly Span[], t: number): boolean => spans.some(([start, end]) => t >= start && t < end);

/** The story time of the last frame, which the static story shows. */
export const LAST = TOTAL - 0.5;

/**
 * The attributes of a piece that shows during the spans. data-in lists the spans as pairs of story
 * times, data-on marks the piece the first frame shows, and data-end marks the pieces the story
 * shows at its end, which is what the static story draws.
 */
export function during(spans: readonly Span[]): Record<string, string | undefined> {
  return {
    "data-in": spans.map(([start, end]) => `${round(start)} ${round(end)}`).join(" "),
    "data-on": inside(spans, 0) ? "" : undefined,
    "data-end": inside(spans, LAST) ? "" : undefined,
  };
}

/** The attributes of a piece that shows for the whole of each step named. */
export const duringSteps = (ids: readonly StepId[]) => during(ids.map(held));

/** A line that draws from story time `at` over `d`, as story.css reads it. */
export const drawn = (at: number, d: number): string => `--at: ${round(at)}; --d: ${round(d)}`;
