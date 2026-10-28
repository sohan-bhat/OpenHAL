/**
 * The wordmark sequence right after the hero, measured in vh of scroll like the landing story. The
 * one-line description and Get started leave while the wordmark comes down, then one step each for
 * H, A and L. In a step the current letter keeps full strength, every other letter fades, and the
 * word slides left so the current letter lands where H stood. A brief under the word says what the
 * part means.
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
    brief:
      "The hardware is any device OpenHAL controls, such as a Klipper 3D printer, a bench power supply or an Arduino board. Each device has a device file that lists the device's channels and the limits a person confirmed.",
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
/** Story time the description, Get started and the labels take to leave. */
export const LEAVES = 10;
/** Story time at which the wordmark starts to come down, once the description has nearly left. */
export const FALLS = 8;
/** Story time each letter holds the stage. */
export const STEP = 40;
/** Story time the other letters take to fade when H starts. */
export const DIM = 8;
/** Story time the word takes to slide from one letter to the next. */
export const SLIDE = 12;
/** The opacity a letter fades to while another letter is current. */
export const LOW = 0.14;

export const TOTAL = AWAY + PARTS.length * STEP;

/** The span a letter's step holds. The last step holds on past the end of the runway. */
export function stepSpan(index: number): Span {
  const from = AWAY + index * STEP;
  return [from, index === PARTS.length - 1 ? NEVER : from + STEP];
}

/** When each brief shows, once its letter is current and the word has stopped. */
export const briefSpan = (index: number): Span => [stepSpan(index)[0] + (index === 0 ? DIM : SLIDE), stepSpan(index)[1]];

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
  const rises: [number, number] = index === 0 ? never : [stepSpan(index)[0], SLIDE];
  const fades: [number, number] = index === PARTS.length - 1 ? never : [stepSpan(index + 1)[0], SLIDE];
  return { dims: index === 0 ? fades : [AWAY, DIM], rises, fades: index === 0 ? never : fades };
}

/** The opacity a letter has at story time t, which story.css computes the same way. */
export function strength(fade: Fading, t: number): number {
  const part = ([start, length]: [number, number]) => Math.min(1, Math.max(0, (t - start) / length));
  return 1 - (1 - LOW) * (part(fade.dims) - part(fade.rises) + part(fade.fades));
}
