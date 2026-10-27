import { CAMERA, TOTAL, stepAt } from "../../lib/story/script";

interface Leg {
  el: HTMLElement;
  from: number;
  to: number;
  last: string;
}

interface State {
  el: Element;
  spans: number[];
  on: boolean;
}

function read(el: HTMLElement, name: string): number {
  const value = parseFloat(el.style.getPropertyValue(name));
  return Number.isFinite(value) ? value : 0;
}

/** Every arrow's leg, and the stretch of story time in which it draws. */
function legs(stage: HTMLElement): Leg[] {
  return Array.from(stage.querySelectorAll<HTMLElement>('[style*="--at"]')).map((el) => {
    const at = read(el, "--at");
    return { el, from: at - 1, to: at + read(el, "--d") + 1, last: "" };
  });
}

function within(spans: number[], t: number): boolean {
  for (let index = 0; index < spans.length; index += 2) if (t >= spans[index] && t < spans[index + 1]) return true;
  return false;
}

/**
 * Pins the stage right under the header while the page scrolls past the runway after it, and turns
 * the scroll position into a point in the story. Every piece of the scene lists the spans of story
 * time it shows in, and the piece carries data-on while the point is inside one of them, so a
 * caption and the arrow it describes change together. story.css cross-fades them, the leaving piece
 * first. Each leg of an arrow reads the point as --t and draws itself, and only the legs that change
 * are touched, so a scroll frame changes no layout. The fit is measured against the small viewport,
 * read from a 100svh probe, so a phone that hides its toolbars while scrolling changes nothing.
 * Without this script, with reduced motion or on a screen too short for the stage, the story is the
 * whole diagram as it ends, followed by the list of steps.
 */
export function story(root: HTMLElement): void {
  const stage = root.querySelector<HTMLElement>(".story-stage");
  const runway = root.querySelector<HTMLElement>(".story-runway");
  if (!stage || !runway) return;
  const header = document.querySelector<HTMLElement>(".site-header");
  const probe = root.querySelector<HTMLElement>(".story-probe");
  const drawing = legs(stage);
  const states: State[] = Array.from(stage.querySelectorAll("[data-in]")).map((el) => ({
    el,
    spans: (el.getAttribute("data-in") ?? "").split(" ").filter(Boolean).map(Number),
    on: el.hasAttribute("data-on"),
  }));
  const media = window.matchMedia(CAMERA);
  let on = false;
  let start = 0;
  let unit = 1;
  let current = -1;
  let frameId = 0;
  let resizing = 0;

  const update = () => {
    frameId = 0;
    if (!on) return;
    const t = Math.min(TOTAL, Math.max(0, (window.scrollY - start) / unit));
    const index = stepAt(t);
    if (index !== current) root.dataset.step = String((current = index));
    for (const state of states) {
      const now = within(state.spans, t);
      if (now !== state.on) state.el.toggleAttribute("data-on", (state.on = now));
    }
    for (const leg of drawing) {
      const value = Math.min(leg.to, Math.max(leg.from, t)).toFixed(2);
      if (value !== leg.last) leg.el.style.setProperty("--t", (leg.last = value));
    }
  };

  const off = () => {
    on = false;
    current = -1;
    root.removeAttribute("data-camera");
    root.removeAttribute("data-ready");
    delete root.dataset.step;
    for (const leg of drawing) {
      leg.last = "";
      leg.el.style.removeProperty("--t");
    }
  };

  const measure = () => {
    if (!media.matches) return off();
    root.setAttribute("data-camera", "");
    const pin = header?.offsetHeight ?? 0;
    root.style.setProperty("--pin", `${pin}px`);
    const view = probe?.offsetHeight || window.innerHeight;
    if (stage.offsetHeight > view - pin) return off();
    root.style.setProperty("--top", `${pin}px`);
    let y = 0;
    for (let el: HTMLElement | null = root; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    start = y - pin;
    unit = Math.max(1, runway.offsetHeight) / TOTAL;
    on = true;
    current = -1;
    for (const leg of drawing) leg.last = "";
    update();
    root.setAttribute("data-ready", "");
  };

  const onScroll = () => {
    if (!frameId) frameId = window.requestAnimationFrame(update);
  };
  const onResize = () => {
    window.cancelAnimationFrame(resizing);
    resizing = window.requestAnimationFrame(measure);
  };

  measure();
  document.fonts?.ready.then(measure);
  document.fonts?.addEventListener("loadingdone", onResize);
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onResize);
  media.addEventListener("change", measure);
}
