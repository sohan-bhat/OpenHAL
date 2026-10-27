/**
 * The landing story as a list of steps, in vh of scroll. The whole diagram stays in view at one
 * size, and each step lights the stations it is about while the others rest. A caption and the
 * state it describes change together at a step's first scroll position and hold until its last.
 * Within a step only the wires move, drawing the message out and its answer back. Scrolling back
 * plays it in reverse.
 */

export type StepId = "intro" | "ask" | "look" | "warm" | "hot" | "loose" | "pause" | "cancel" | "wake" | "end";

export type Station = "client" | "hub" | "kernel" | "driver" | "printer" | "camera";

export interface Step {
  id: StepId;
  length: number;
  lit: Station[];
}

export const CAMERA =
  "(prefers-reduced-motion: no-preference) and (min-width: 1024px) and (min-height: 768px), (prefers-reduced-motion: no-preference) and (max-width: 1023.98px) and (min-height: 800px)";

export const STEPS: readonly Step[] = [
  { id: "intro", length: 20, lit: [] },
  { id: "ask", length: 44, lit: ["client"] },
  { id: "look", length: 50, lit: ["client", "driver", "camera"] },
  { id: "warm", length: 50, lit: ["hub", "kernel", "printer"] },
  { id: "hot", length: 50, lit: ["client", "hub", "kernel"] },
  { id: "loose", length: 50, lit: ["client", "driver", "camera"] },
  { id: "pause", length: 50, lit: ["kernel", "driver", "printer"] },
  { id: "cancel", length: 50, lit: ["client", "hub", "kernel"] },
  { id: "wake", length: 44, lit: ["hub", "printer", "camera"] },
  { id: "end", length: 36, lit: ["client", "hub", "kernel", "driver", "printer", "camera"] },
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

/** The steps given, as the data-in and data-lit attributes list them. */
export const steps = (ids: readonly StepId[]): string => ids.map((id) => step(id).index).join(" ");

/** Every step from `first` up to and including `last`. */
export function span(first: StepId, last: StepId = "end"): StepId[] {
  return PLACED.slice(step(first).index, step(last).index + 1).map((item) => item.id);
}

/** The steps whose state shows a piece, as attributes, with data-on set when `now` is one of them. */
export function shown(ids: readonly StepId[], now?: number): Record<string, string | undefined> {
  const list = steps(ids);
  return { "data-in": list, "data-on": now !== undefined && list.split(" ").includes(String(now)) ? "" : undefined };
}

/** The steps that light a station, as attributes, with data-on set when `now` is one of them. */
export function lit(station: Station, now?: number): Record<string, string | undefined> {
  const ids = PLACED.filter((item) => item.lit.includes(station)).map((item) => item.id);
  const list = steps(ids);
  return { "data-lit": list, "data-on": now !== undefined && list.split(" ").includes(String(now)) ? "" : undefined };
}

export const NEVER = 100000;

const round = (n: number) => Math.round(n * 100) / 100;

/** A wire fill that draws from `at` over `length` and is gone by `out`, as story.css reads it. */
export function run(at: number, length: number, out = NEVER): string {
  return `--at: ${round(at)}; --d: ${length}; --out: ${round(out)}; --f: 2`;
}
