import * as React from "react";
import { LazyMotion, domAnimation, useReducedMotion, type Transition } from "motion/react";

/** The site's ease, --ease in design/tokens.css, which never passes its end. */
export const EASE: [number, number, number, number] = [0.2, 0, 0, 1];

/** How long a part takes to open and to close, in seconds (docs/DESIGN.md, Motion, pattern 9). */
export const OPEN = 0.2;
export const CLOSE = 0.15;

/**
 * Motion's animation features for every island, loaded with the island rather than with the page.
 * Strict mode keeps every component on the small `m` elements.
 */
export function MotionRoot({ children }: { children: React.ReactNode }) {
  return (
    <LazyMotion features={domAnimation} strict>
      {children}
    </LazyMotion>
  );
}

/** The open and close transitions, which take no time when a person asked for reduced motion. */
export function useTimings(): { open: Transition; close: Transition; still: boolean } {
  const still = useReducedMotion() ?? false;
  return React.useMemo(
    () => ({
      open: { duration: still ? 0 : OPEN, ease: EASE },
      close: { duration: still ? 0 : CLOSE, ease: EASE },
      still,
    }),
    [still],
  );
}
