import { CAMERA } from "../../lib/story/camera";

interface Piece {
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

export interface Scene {
  /** The element that pins under the header. */
  stage: string;
  /** The empty block after the stage whose height is the scene's length of scroll. */
  runway: string;
  /** Whether the scene turns off when the stage is taller than the screen under the header. */
  fits?: boolean;
  /** Measurements a scene takes from its own layout before it plays, given the header's height. */
  layout?: (pin: number) => void;
  /** Moves what the scene drives outside its own root, given the story time and the scroll position, each time the scene updates. */
  play?: (t: number, y: number) => void;
  /** Puts back what `play` moved, when the scene stops playing. */
  rest?: () => void;
}

function read(el: HTMLElement, name: string): number {
  const value = parseFloat(el.style.getPropertyValue(name));
  return Number.isFinite(value) ? value : 0;
}

function within(spans: number[], t: number): boolean {
  for (let index = 0; index < spans.length; index += 2) if (t >= spans[index] && t < spans[index + 1]) return true;
  return false;
}

/**
 * Pins a scene's stage right under the header while the page scrolls past the runway after it,
 * and turns the scroll position into story time, from 0 to the root's data-total. Every piece that
 * lists spans of story time in data-in carries data-on while the time is inside one of them, and
 * the stylesheet cross-fades it. Every piece with an inline --at and --d reads the time as --t,
 * held to the stretch in which the piece changes, and moves itself with transforms and opacity,
 * so a scroll frame changes no layout. The fit is measured against the small viewport, read from a
 * 100svh probe, so a phone that hides its toolbars while scrolling changes nothing. Without this
 * script, with reduced motion or on a screen too short for the stage, the scene is still.
 */
export function scene(root: HTMLElement, options: Scene): void {
  const stage = root.querySelector<HTMLElement>(options.stage);
  const runway = root.querySelector<HTMLElement>(options.runway);
  if (!stage || !runway) return;
  const total = Number(root.dataset.total) || 1;
  const header = document.querySelector<HTMLElement>(".site-header");
  const probe = document.querySelector<HTMLElement>(".story-probe");
  const pieces: Piece[] = [root, ...root.querySelectorAll<HTMLElement>('[style*="--at:"]')]
    .filter((el) => el.style.getPropertyValue("--at"))
    .map((el) => {
      const at = read(el, "--at");
      return { el, from: at - 1, to: at + read(el, "--d") + 1, last: "" };
    });
  const states: State[] = Array.from(root.querySelectorAll("[data-in]")).map((el) => ({
    el,
    spans: (el.getAttribute("data-in") ?? "").split(" ").filter(Boolean).map(Number),
    on: el.hasAttribute("data-on"),
  }));
  const media = window.matchMedia(CAMERA);
  let on = false;
  let start = 0;
  let unit = 1;
  let frameId = 0;
  let resizing = 0;

  const update = () => {
    frameId = 0;
    if (!on) return;
    const y = window.scrollY;
    const t = Math.min(total, Math.max(0, (y - start) / unit));
    options.play?.(t, y);
    for (const state of states) {
      const now = within(state.spans, t);
      if (now !== state.on) state.el.toggleAttribute("data-on", (state.on = now));
    }
    for (const piece of pieces) {
      const value = Math.min(piece.to, Math.max(piece.from, t)).toFixed(2);
      if (value !== piece.last) piece.el.style.setProperty("--t", (piece.last = value));
    }
  };

  const off = () => {
    on = false;
    options.rest?.();
    root.removeAttribute("data-camera");
    root.removeAttribute("data-ready");
    for (const piece of pieces) {
      piece.last = "";
      piece.el.style.removeProperty("--t");
    }
  };

  const measure = () => {
    if (!media.matches) return off();
    root.setAttribute("data-camera", "");
    const pin = header?.offsetHeight ?? 0;
    root.style.setProperty("--pin", `${pin}px`);
    options.layout?.(pin);
    const view = probe?.offsetHeight || window.innerHeight;
    if (options.fits && stage.offsetHeight > view - pin + 1) return off();
    root.style.setProperty("--top", `${pin}px`);
    let y = 0;
    for (let el: HTMLElement | null = root; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    start = y - pin;
    unit = Math.max(1, runway.offsetHeight) / total;
    on = true;
    for (const piece of pieces) piece.last = "";
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
