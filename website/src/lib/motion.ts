import type { animate } from "motion/mini";

type Frames = Parameters<typeof animate>[1];
type Options = NonNullable<Parameters<typeof animate>[2]>;

/** How long a part takes to open and to close, in seconds, and the site's ease, --ease in design/tokens.css. */
export const OPEN = 0.2;
export const CLOSE = 0.15;
const EASE: [number, number, number, number] = [0.2, 0, 0, 1];

const reduce = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : undefined;
let library: Promise<typeof import("motion/mini")> | undefined;

/** True when a person asked for reduced motion, so every part opens and closes at once. */
export const still = (): boolean => reduce?.matches ?? true;

/** Starts loading Motion's mini animate, once, so the first interaction finds it ready. */
export function warm(): Promise<typeof import("motion/mini")> {
  library ??= import("motion/mini").catch((error: unknown) => {
    library = undefined;
    throw error;
  });
  return library;
}

/**
 * Animates an element with Motion, resolving when the animation ends. An animation that a newer
 * one on the same element and property replaces never resolves, so a caller that waits on it
 * leaves the cleanup to the newer one. If Motion fails to load, it resolves at once.
 */
export async function tween(element: Element, frames: Frames, duration: number, options: Options = {}): Promise<void> {
  let motion: typeof import("motion/mini");
  try {
    motion = await warm();
  } catch {
    return;
  }
  await motion.animate(element, frames, { duration, ease: EASE, ...options }).finished;
}

/** Hands the listed properties back to the stylesheet once an animation has set them inline. */
export function release(element: HTMLElement | SVGElement, ...names: string[]): void {
  for (const name of names) element.style.removeProperty(name);
}
