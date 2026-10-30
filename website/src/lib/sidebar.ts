const KEY = "openhal-sidebar";
const EASE: [number, number, number, number] = [0.2, 0, 0, 1];
const OPEN = 0.2;
const CLOSE = 0.15;

type Frames = Record<string, [string | number, string | number]>;

const listeners = new Set<() => void>();
const running = new Map<HTMLElement, { cancel(): void; names: string[] }>();
let library: Promise<typeof import("motion/mini")> | undefined;
let turns = 0;

/** Motion's small animate, loaded the first time something moves, so reduced motion never loads it. */
const motion = () => (library ??= import("motion/mini"));

const root = () => document.documentElement;
const pane = () => document.getElementById("starlight__sidebar");
const still = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const wide = () => matchMedia("(min-width: 50rem)").matches;

/** True while a person keeps the documentation sidebar hidden, which the page's head script reads first. */
export function isCollapsed(): boolean {
  return typeof document !== "undefined" && root().dataset.sidebar === "collapsed";
}

/** True while the hidden sidebar shows for a moment because the pointer rests at the left edge. */
export function isPeeking(): boolean {
  return typeof document !== "undefined" && root().hasAttribute("data-sidebar-peek");
}

/** Calls `listener` whenever the sidebar is hidden, shown, or peeks, and returns how to stop. */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const tell = () => {
  for (const listener of listeners) listener();
};

/** Ends an element's motion where it is and hands its style back to the stylesheet. */
function stop(element: HTMLElement): void {
  const handle = running.get(element);
  if (!handle) return;
  handle.cancel();
  running.delete(element);
  for (const name of handle.names) element.style.removeProperty(name);
}

/**
 * Moves an element through its frames with Motion and resolves true once the motion ends. The first
 * frame applies at once, so nothing shows in its final place while Motion loads, and the element
 * hands its style back to the stylesheet whether the motion ends, fails to load or gives way.
 */
function play(element: HTMLElement, frames: Frames, duration: number): Promise<boolean> {
  stop(element);
  for (const [name, [from]] of Object.entries(frames)) element.style.setProperty(name, String(from));
  let animation: { cancel(): void; finished: Promise<unknown> } | undefined;
  let cancelled = false;
  const handle = {
    names: Object.keys(frames),
    cancel: () => {
      cancelled = true;
      animation?.cancel();
    },
  };
  running.set(element, handle);
  const release = (finished: boolean) => {
    if (running.get(element) !== handle) return false;
    running.delete(element);
    for (const name of Object.keys(frames)) element.style.removeProperty(name);
    return finished;
  };
  return motion().then(
    ({ animate }) => {
      if (cancelled) return false;
      animation = animate(element, frames, { duration, ease: EASE });
      return animation.finished.then(
        () => release(true),
        () => false,
      );
    },
    () => release(false),
  );
}

/** The parts of a page that move over when the sidebar hides or shows: the content and the outline. */
function movers(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("main, .right-sidebar, mobile-starlight-toc nav")].filter((element) => element.getClientRects().length);
}

/** Keeps the hidden sidebar out of the tab order and away from screen readers, except while it peeks. */
function settle(): void {
  const element = pane();
  if (!element || !wide()) return;
  element.inert = isCollapsed() && !isPeeking();
}

/**
 * Hides or shows the documentation sidebar and remembers the choice in this browser. The sidebar
 * slides with Motion while the content and the outline move over, using transforms only, in 200 ms
 * to show and 150 ms to hide, and with reduced motion it switches at once. A press of the button
 * hands focus to the other button, which takes the same place.
 */
export function setCollapsed(next: boolean, { handoff = false }: { handoff?: boolean } = {}): void {
  if (next === isCollapsed()) return;
  const element = pane();
  const moving = wide() && !still();
  const peeked = isPeeking();
  const before = moving ? movers().map((mover) => [mover, mover.getBoundingClientRect().left] as const) : [];
  const from = element && moving ? getComputedStyle(element).transform : "none";
  for (const [mover] of before) stop(mover);
  if (element) stop(element);
  const hadFocus = element?.contains(document.activeElement) ?? false;

  root().removeAttribute("data-sidebar-peek");
  root().removeAttribute("data-sidebar-leaving");
  if (next) root().dataset.sidebar = "collapsed";
  else delete root().dataset.sidebar;
  try {
    localStorage.setItem(KEY, next ? "collapsed" : "");
  } catch {}
  settle();
  tell();

  const focus = next ? "[data-sidebar-show]" : "[data-sidebar-hide]";
  if (handoff || (next ? hadFocus : document.activeElement?.matches("[data-sidebar-show]"))) document.querySelector<HTMLElement>(focus)?.focus({ preventScroll: true });
  if (!moving) return;

  const duration = next ? CLOSE : OPEN;
  const turn = ++turns;
  root().setAttribute("data-sidebar-moving", "");
  const done: Array<Promise<boolean>> = [];
  for (const [mover, left] of before) {
    const shift = left - mover.getBoundingClientRect().left;
    if (Math.abs(shift) > 0.5) done.push(play(mover, { transform: [`translateX(${shift}px)`, "translateX(0px)"] }, duration));
  }
  if (element && !peeked) {
    const start = from === "none" ? (next ? "translateX(0px)" : "translateX(-100%)") : from;
    done.push(play(element, { transform: [start, next ? "translateX(-100%)" : "translateX(0px)"] }, duration));
  }
  void Promise.all(done).then(() => {
    if (turn === turns) root().removeAttribute("data-sidebar-moving");
  });
}

/**
 * Brings the hidden sidebar in for a moment as a narrower inset panel, or sends it away. It fades
 * and slides 12 px in 200 ms and leaves in 150 ms, staying drawn until it has gone, and a change of
 * mind midway turns it back from where it is.
 */
export function setPeek(on: boolean): void {
  const element = pane();
  if (!element || !isCollapsed() || !wide() || on === (isPeeking() && !root().hasAttribute("data-sidebar-leaving"))) return;
  const midway = running.has(element);
  const now = getComputedStyle(element);
  const opacity = midway ? Number(now.opacity) : on ? 0 : 1;
  const transform = midway ? now.transform : on ? "translateX(-12px)" : "translateX(0px)";
  stop(element);
  if (on) {
    root().removeAttribute("data-sidebar-leaving");
    root().setAttribute("data-sidebar-peek", "");
    settle();
    tell();
    if (!still()) void play(element, { opacity: [opacity, 1], transform: [transform, "translateX(0px)"] }, OPEN);
    return;
  }
  const leave = () => {
    root().removeAttribute("data-sidebar-peek");
    root().removeAttribute("data-sidebar-leaving");
    settle();
    tell();
  };
  if (still()) return leave();
  root().setAttribute("data-sidebar-leaving", "");
  void play(element, { opacity: [opacity, 0], transform: [transform, "translateX(-8px)"] }, CLOSE).then((finished) => {
    if (finished || !running.has(element)) leave();
  });
}

/** Applies the saved state to the sidebar's tab order once the page's script runs. */
export function start(): void {
  settle();
  matchMedia("(min-width: 50rem)").addEventListener("change", () => {
    const element = pane();
    if (element && !wide()) element.inert = false;
    settle();
  });
}
