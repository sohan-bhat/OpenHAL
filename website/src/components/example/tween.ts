import { animate } from "motion";

/** Moves a number from one value to another with Motion, linearly, calling `update` on each frame. */
export function tween(from: number, to: number, duration: number, update: (value: number) => void): { stop: () => void } {
  return animate(from, to, { duration, ease: "linear", onUpdate: update });
}
