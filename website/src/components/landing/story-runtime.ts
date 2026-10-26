import { cameraAt, framing, transform, union, type Box, type Cam, type Framed } from "../../lib/story/camera";
import { CAMERA, NEVER, PLACED, TOTAL } from "../../lib/story/script";

const SETTLE = 150;

interface Track {
  el: HTMLElement;
  spans: Array<[number, number]>;
  last: string;
}

function rectIn(el: HTMLElement, scene: HTMLElement): Box {
  let x = 0;
  let y = 0;
  for (let node: HTMLElement | null = el; node && node !== scene; node = node.offsetParent as HTMLElement | null) {
    x += node.offsetLeft;
    y += node.offsetTop;
  }
  return { x, y, w: el.offsetWidth, h: el.offsetHeight };
}

function read(el: HTMLElement, name: string, fallback: number): number {
  const value = parseFloat(el.style.getPropertyValue(name));
  return Number.isFinite(value) ? value : fallback;
}

/** Every piece of the stage that changes with the story, and the stretches of story time in which it does. */
function tracks(stage: HTMLElement): Track[] {
  return Array.from(stage.querySelectorAll<HTMLElement>('[style*="--at"], [style*="--out"]')).map((el) => {
    const fade = read(el, "--f", 2);
    const length = read(el, "--d", 0);
    const points: Array<[number, number]> = [];
    const arrive = read(el, "--at", NEVER);
    const leave = read(el, "--out", NEVER);
    if (Math.abs(arrive) < NEVER) points.push([arrive - 1, arrive + Math.max(fade, length) + 1]);
    if (Math.abs(leave) < NEVER) points.push([leave - fade - 1, leave + 1]);
    const spans: Array<[number, number]> = [];
    for (const point of points.sort((a, b) => a[0] - b[0])) {
      const last = spans[spans.length - 1];
      if (last && point[0] <= last[1]) last[1] = Math.max(last[1], point[1]);
      else spans.push(point);
    }
    return { el, spans: spans.length ? spans : [[0, 0]], last: "" };
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
 * Pins the stage under the header and lets the scroll position pick a point in the shot list. The
 * camera is written as one transform on the scene, and the point as --t on each piece that changes
 * then. story.css turns --t into opacity against a piece's --at and --out, arriving over --f after
 * --at and gone by --out, so a piece and the one that replaces it never overlap, and into a fill's
 * length against --at over --d. Targets are measured only on load, on resize and when fonts
 * arrive, so a scroll frame reads nothing but the scroll position. Without this script, or with
 * reduced motion, the story is the list of steps under the stage.
 */
export function story(root: HTMLElement): void {
  const stage = root.querySelector<HTMLElement>(".story-stage");
  const band = root.querySelector<HTMLElement>(".story-band");
  const scene = root.querySelector<HTMLElement>(".story-scene");
  if (!stage || !band || !scene) return;
  const header = document.querySelector<HTMLElement>(".site-header");
  const stations = Array.from(scene.querySelectorAll<HTMLElement>("[data-cam]"));
  const pieces = tracks(stage);
  const media = window.matchMedia(CAMERA);
  let on = false;
  let start = 0;
  let unit = 1;
  let frame: Box = { x: 0, y: 0, w: 1, h: 1 };
  let shots: Framed[] = [];
  let cam: Cam = { x: 0, y: 0, z: 1 };
  let frameId = 0;
  let resizing = 0;
  let settle = 0;
  let moving = false;
  let still = "";

  const write = (sharp: boolean) => {
    const { x, y, z } = transform(cam, frame);
    const px = (n: number) => (sharp ? Math.round(n * window.devicePixelRatio) / window.devicePixelRatio : n).toFixed(2);
    scene.style.transform = `translate(${px(x)}px, ${px(y)}px) scale(${z.toFixed(4)})`;
  };

  const rest = () => {
    moving = false;
    scene.style.removeProperty("will-change");
    write(true);
  };

  const update = () => {
    frameId = 0;
    if (!on) return;
    const t = Math.min(TOTAL, Math.max(0, (window.scrollY - start) / unit));
    for (const piece of pieces) {
      const value = held(piece.spans, t).toFixed(2);
      if (value !== piece.last) piece.el.style.setProperty("--t", (piece.last = value));
    }
    cam = cameraAt(t, shots, frame);
    const key = `${cam.x.toFixed(2)} ${cam.y.toFixed(2)} ${cam.z.toFixed(4)}`;
    if (key === still) return;
    still = key;
    if (!moving) {
      moving = true;
      scene.style.willChange = "transform";
    }
    write(false);
    window.clearTimeout(settle);
    settle = window.setTimeout(rest, SETTLE);
  };

  const measure = () => {
    on = media.matches;
    root.toggleAttribute("data-camera", on);
    window.clearTimeout(settle);
    moving = false;
    still = "";
    pieces.forEach((piece) => (piece.last = ""));
    if (!on) {
      root.removeAttribute("data-ready");
      pieces.forEach((piece) => piece.el.style.removeProperty("--t"));
      scene.style.removeProperty("transform");
      scene.style.removeProperty("will-change");
      return;
    }
    const pin = header?.offsetHeight ?? 0;
    root.style.setProperty("--pin", `${pin}px`);
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const phone = w < 768;
    const side = phone ? 16 : 48;
    const top = band.offsetHeight + (phone ? 4 : 8);
    const bottom = phone ? 16 : 32;
    frame = { x: side, y: top, w: w - 2 * side, h: h - top - bottom };
    const column = getComputedStyle(scene).flexDirection === "column";
    const boxes = new Map(stations.map((station) => [station.dataset.cam, rectIn(station, scene)]));
    const whole: Box = { x: 0, y: 0, w: scene.offsetWidth, h: scene.offsetHeight };
    shots = PLACED.map((shot) => {
      const target = (column && shot.column) || shot.target;
      const box = target === "scene" ? whole : union(target.map((name) => boxes.get(name) ?? whole));
      const fit = column && target !== "scene" ? { ...shot, min: Math.max(shot.min ?? 0, 1) } : shot;
      return { glideFrom: shot.glideFrom, dwellFrom: shot.dwellFrom, end: shot.end, ...framing(box, frame, fit) };
    });
    let y = 0;
    for (let el: HTMLElement | null = root; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    start = y - pin;
    unit = Math.max(1, root.offsetHeight - stage.offsetHeight) / TOTAL;
    update();
    window.clearTimeout(settle);
    rest();
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
