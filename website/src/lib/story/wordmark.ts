/**
 * The wordmark sequence right after the hero, measured in vh of scroll like the landing story. The
 * first scroll drops the demo's opening away, the one-line description and Get started leave, and
 * the wordmark comes down and moves right until H stands where L stands at rest, then one step
 * each for H, A and L. In a step the current letter keeps full strength and every other letter
 * fades, and between letters the whole word slides left, the owner's idea, so each current letter
 * lands on the same spot and the word ends at rest under L, never past either edge of the column.
 * A brief under that spot says what the part means.
 */

import { NEVER, type Span } from "./script";

export type Letter = "H" | "A" | "L";

export interface Part {
  letter: Letter;
  label: string;
  brief: string;
}

export const PARTS: readonly Part[] = [
  {
    letter: "H",
    label: "[hardware]",
    brief: "The hardware is any device OpenHAL controls. Each device has a device file that lists the device's channels and the limits a person confirmed.",
  },
  {
    letter: "A",
    label: "[abstraction]",
    brief:
      "A hardware abstraction layer gives every device the same interface, so an agent reads and changes a 3D printer, a bench power supply or an Arduino board with the same few requests while the device file and the driver handle the differences.",
  },
  {
    letter: "L",
    label: "[layer]",
    brief:
      "The layer is the hub between the agent and the hardware, where the safety kernel checks every request against the device file's limits before a driver sends a command to the device.",
  },
];

/** Story time for the description and Get started to leave and the wordmark to come down. */
export const AWAY = 24;
/** Story time the demo's opening takes to drop away on the first scroll, the small diagram and the step count's row together. */
export const DROP = 12;
/** How far the demo's opening drops while the opening fades, as a share of the screen's height. */
export const FALL = 0.22;
/** Story time the description, Get started and the labels take to leave. */
export const LEAVES = 10;
/** Story time at which the wordmark starts to come down, once the description has nearly left. */
export const FALLS = 8;
/** Story time each letter holds the stage. */
export const STEP = 24;
/** Story time the other letters take to fade when H starts. */
export const DIM = 6;
/** Story time one letter takes to hand full strength to the next. */
export const SWAP = 6;
/** The opacity a letter fades to while another letter is current. */
export const LOW = 0.14;

export const TOTAL = AWAY + PARTS.length * STEP;

/** The span a letter's step holds. The last step holds on past the end of the runway. */
export function stepSpan(index: number): Span {
  const from = AWAY + index * STEP;
  return [from, index === PARTS.length - 1 ? NEVER : from + STEP];
}

/** When each brief shows, once its letter has full strength. */
export const briefSpan = (index: number): Span => [stepSpan(index)[0] + (index === 0 ? DIM : SWAP), stepSpan(index)[1]];

/**
 * When a letter of the word fades and comes back, as the windows story.css reads. A letter fades
 * from full strength over `dims`, rises again over `rises` and fades again over `fades`, each a
 * start and a length in story time, and a window that never comes starts at NEVER.
 */
export interface Fading {
  dims: [number, number];
  rises: [number, number];
  fades: [number, number];
}

const never: [number, number] = [NEVER, 1];

export function fading(word: string, at: number): Fading {
  const index = PARTS.findIndex((part) => word.lastIndexOf(part.letter) === at);
  if (index < 0) return { dims: [AWAY, DIM], rises: never, fades: never };
  const rises: [number, number] = index === 0 ? never : [stepSpan(index)[0], SWAP];
  const fades: [number, number] = index === PARTS.length - 1 ? never : [stepSpan(index + 1)[0], SWAP];
  return { dims: index === 0 ? fades : [AWAY, DIM], rises, fades: index === 0 ? never : fades };
}

/** The opacity a letter has at story time t, which story.css computes the same way. */
export function strength(fade: Fading, t: number): number {
  const part = ([start, length]: [number, number]) => Math.min(1, Math.max(0, (t - start) / length));
  return 1 - (1 - LOW) * (part(fade.dims) - part(fade.rises) + part(fade.fades));
}
