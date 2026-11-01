/** Where this browser remembers the Smooth scrolling choice. */
export const KEY = "openhal:smooth-scroll";

/** The window event the Smooth scrolling switch sends when a person turns smooth scrolling on or off. */
export const CHANGED = "openhal:smooth-scroll-changed";

const REDUCE = "(prefers-reduced-motion: reduce)";

function stored(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Remembers the choice in this browser and tells the page, which starts or stops the easing. */
export function choose(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    return;
  } finally {
    window.dispatchEvent(new Event(CHANGED));
  }
}

/** Whether the switch is on and whether a person can turn it, given the stored choice and reduced motion. */
export function smoothState(): { on: boolean; disabled: boolean } {
  const reduce = window.matchMedia(REDUCE).matches;
  return { on: !reduce && stored() !== "off", disabled: reduce };
}

/** Calls back whenever reduced motion turns on or off, and returns a function that stops listening. */
export function onReduceChange(callback: () => void): () => void {
  const reduce = window.matchMedia(REDUCE);
  reduce.addEventListener("change", callback);
  return () => reduce.removeEventListener("change", callback);
}

function idle(run: () => void): void {
  if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(run, { timeout: 2000 });
  else globalThis.setTimeout(run, 200);
}

/**
 * Runs the easing on the home page while smooth scrolling is on. Smooth scrolling is on unless the
 * person turned it off, which this browser remembers, and always off under prefers-reduced-motion.
 * The easing loads once the page is idle, and only while smooth scrolling is on.
 */
export function smoothScrolling(): void {
  let stop: (() => void) | null = null;
  let loading = false;

  const apply = () => {
    const { on } = smoothState();
    if (on && !stop && !loading) {
      loading = true;
      idle(() => {
        import("./smooth-scroll").then(({ smooth }) => {
          loading = false;
          if (smoothState().on && !stop) stop = smooth();
        });
      });
    }
    if (!on && stop) {
      stop();
      stop = null;
    }
  };

  window.addEventListener(CHANGED, apply);
  onReduceChange(apply);
  apply();
}
