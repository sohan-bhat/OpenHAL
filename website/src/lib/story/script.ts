/**
 * The landing story as a list of steps, in vh of scroll. The whole diagram stays in view at one
 * size, and each step lights every station its message passes while the others rest. A caption and
 * the state it describes change together at a step's first scroll position and hold until its last.
 * Within a step only the wires move, drawing the message out and its answer back. Scrolling back
 * plays it in reverse.
 */

export type StepId = "intro" | "ask" | "look" | "warm" | "hot" | "loose" | "pause" | "cancel" | "approve" | "end";

export type Station = "client" | "hub" | "kernel" | "driver" | "printer" | "camera";

export interface Step {
  id: StepId;
  length: number;
  lit: Station[];
}

/**
 * Screens tall enough that the stage may play. The height is under the shortest stage of any
 * layout with the header, so the story never turns off while a phone hides its toolbars.
 * Story.astro and the runtime still check the fit, the whole stage first and then the short one.
 */
export const CAMERA = "(prefers-reduced-motion: no-preference) and (min-height: 600px)";

export const STEPS: readonly Step[] = [
  { id: "intro", length: 20, lit: [] },
  { id: "ask", length: 44, lit: ["client"] },
  { id: "look", length: 50, lit: ["client", "hub", "kernel", "driver", "camera"] },
  { id: "warm", length: 50, lit: ["client", "hub", "kernel", "driver", "printer"] },
  { id: "hot", length: 50, lit: ["client", "hub", "kernel"] },
  { id: "loose", length: 50, lit: ["client", "hub", "kernel", "driver", "camera"] },
  { id: "pause", length: 50, lit: ["client", "hub", "kernel", "driver", "printer"] },
  { id: "cancel", length: 50, lit: ["client", "hub", "kernel"] },
  { id: "approve", length: 50, lit: ["hub", "kernel", "driver", "printer"] },
  { id: "end", length: 40, lit: ["client", "hub", "kernel", "driver", "printer", "camera"] },
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

/** Each value a piece takes, with the steps that show it, from one value for every step. */
export function runs(values: Record<StepId, string>): Array<{ text: string; in: StepId[] }> {
  const out: Array<{ text: string; in: StepId[] }> = [];
  for (const item of PLACED) {
    const text = values[item.id];
    const found = out.find((entry) => entry.text === text);
    if (found) found.in.push(item.id);
    else out.push({ text, in: [item.id] });
  }
  return out;
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
