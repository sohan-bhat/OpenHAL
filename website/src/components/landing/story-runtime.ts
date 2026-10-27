import { CAMERA, NEVER, TOTAL, stepAt } from "../../lib/story/script";

interface Track {
  el: HTMLElement;
  spans: Array<[number, number]>;
  last: string;
}

interface State {
  el: HTMLElement;
  steps: number[];
}

function read(el: HTMLElement, name: string, fallback: number): number {
  const value = parseFloat(el.style.getPropertyValue(name));
  return Number.isFinite(value) ? value : fallback;
}

/** Every wire fill, and the stretches of story time in which it changes. */
function tracks(stage: HTMLElement): Track[] {
  return Array.from(stage.querySelectorAll<HTMLElement>('[style*="--at"]')).map((el) => {
    const fade = read(el, "--f", 2);
    const length = read(el, "--d", 0);
    const arrive = read(el, "--at", NEVER);
    const leave = read(el, "--out", NEVER);
    const spans: Array<[number, number]> = [[arrive - 1, arrive + length + 1]];
    if (leave < NEVER) spans.push([leave - fade - 1, leave + 1]);
    return { el, spans, last: "" };
  });
}

function held(spans: Array<[number, number]>, t: number): number {
  let value = spans[0][0];
  for (const [start, end] of spans) {
    if (t < start) break;
    value = Math.min(t, end);
  }
  return value;
}

/**
 * Pins the stage, centered under the header, while the page scrolls past the runway after it, and
 * turns the scroll position into a point in the story. The step that holds that point is written
 * as data-step on the story and as data-on on every piece and station that shows in it, so a
 * caption and its state change together. story.css cross-fades them, the leaving piece first. The
 * wire fills read the point as --t, set only on the fills that change, so a scroll frame touches
 * nothing else. Without this script, with reduced motion or on a screen too short for the stage,
 * the story is the list of steps after the runway.
 */
export function story(root: HTMLElement): void {
  const stage = root.querySelector<HTMLElement>(".story-stage");
  const runway = root.querySelector<HTMLElement>(".story-runway");
  if (!stage || !runway) return;
  const header = document.querySelector<HTMLElement>(".site-header");
  const pieces = tracks(stage);
  const states: State[] = Array.from(stage.querySelectorAll<HTMLElement>("[data-in], [data-lit]")).map((el) => ({
    el,
    steps: (el.dataset.in ?? el.dataset.lit ?? "").split(" ").filter(Boolean).map(Number),
  }));
  const media = window.matchMedia(CAMERA);
  let on = false;
  let start = 0;
  let unit = 1;
  let current = -1;
  let frameId = 0;
  let resizing = 0;

  const show = (index: number) => {
    if (index === current) return;
    current = index;
    root.dataset.step = String(index);
    for (const state of states) state.el.toggleAttribute("data-on", state.steps.includes(index));
  };

  const update = () => {
    frameId = 0;
    if (!on) return;
    const t = Math.min(TOTAL, Math.max(0, (window.scrollY - start) / unit));
    show(stepAt(t));
    for (const piece of pieces) {
      const value = held(piece.spans, t).toFixed(2);
      if (value !== piece.last) piece.el.style.setProperty("--t", (piece.last = value));
    }
  };

  const off = () => {
    on = false;
    current = -1;
    root.removeAttribute("data-camera");
    root.removeAttribute("data-ready");
    delete root.dataset.step;
    pieces.forEach((piece) => {
      piece.last = "";
      piece.el.style.removeProperty("--t");
    });
  };

  const measure = () => {
    if (!media.matches) return off();
    root.setAttribute("data-camera", "");
    const pin = header?.offsetHeight ?? 0;
    root.style.setProperty("--pin", `${pin}px`);
    const height = stage.offsetHeight;
    if (height > window.innerHeight - pin) return off();
    const top = Math.max(pin, Math.round((window.innerHeight + pin - height) / 2));
    root.style.setProperty("--top", `${top}px`);
    let y = 0;
    for (let el: HTMLElement | null = root; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    start = y - top;
    unit = Math.max(1, runway.offsetHeight) / TOTAL;
    on = true;
    current = -1;
    pieces.forEach((piece) => (piece.last = ""));
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
