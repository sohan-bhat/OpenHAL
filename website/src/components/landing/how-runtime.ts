import { scroll } from "motion";
import { animate } from "motion/mini";
import { CAMERA } from "../../lib/story/camera";

type Kind = "line" | "dash" | "show" | "hide";

/** What each kind of piece does as it plays, from its first value to its last. */
const FRAMES: Record<Kind, Record<string, [string | number, string | number]>> = {
  line: { transform: ["scaleX(0)", "scaleX(1)"] },
  dash: { clipPath: ["inset(0 0 0 100%)", "inset(0 0 0 0%)"] },
  show: { opacity: [0, 1] },
  hide: { opacity: [1, 0] },
};

/**
 * Plays How it works with the scroll. The stage pins under the header while the page scrolls past
 * the track, and Motion ties every piece to the scroll through the track, so an arrow draws as the
 * page scrolls and scrolling back plays it in reverse. Each piece names its kind and the stretch of
 * the scroll it changes in, `data-draw="line 0.04 0.0733"`. The progress runs from the moment the
 * stage pins under the header to the moment the stage lets go, measured the same way in every
 * browser, and the step count and the step on show follow the same progress. With reduced motion,
 * on a screen too short for the stage, or before this runs, the steps are three still panels.
 */
export function howItWorks(root: HTMLElement): void {
  const track = root.querySelector<HTMLElement>(".how-track");
  const stage = root.querySelector<HTMLElement>(".how-stage");
  const count = Number(root.dataset.count) || 1;
  const media = window.matchMedia(CAMERA);
  let stops: Array<() => void> = [];
  let played: Array<{ cancel: () => void }> = [];

  const still = () => {
    for (const stop of stops) stop();
    for (const animation of played) animation.cancel();
    stops = [];
    played = [];
    root.removeAttribute("data-motion");
    root.removeAttribute("data-step");
  };

  const play = () => {
    still();
    if (!track || !stage || !media.matches) return;
    root.setAttribute("data-motion", "");
    root.setAttribute("data-step", "1");
    if (stage.scrollHeight > stage.clientHeight + 1) return still();
    const pin = document.querySelector<HTMLElement>("header.header")?.offsetHeight ?? 0;
    const offset: [`start ${number}px`, "end end"] = [`start ${pin}px`, "end end"];
    const options = { target: track, offset };
    for (const piece of root.querySelectorAll<HTMLElement>("[data-draw]")) {
      const [kind, start, length] = (piece.dataset.draw ?? "").split(" ");
      const frames = FRAMES[kind as Kind];
      if (!frames) continue;
      const from = Number(start);
      const to = Math.min(1, from + Number(length));
      const keyframes = Object.fromEntries(Object.entries(frames).map(([name, [first, last]]) => [name, [first, first, last, last]]));
      const animation = animate(piece, keyframes, { duration: 1, ease: "linear", times: [0, from, to, 1] });
      played.push(animation);
      stops.push(scroll(animation, options));
    }
    stops.push(
      scroll((progress: number) => {
        const step = String(Math.min(count, Math.floor(progress * count) + 1));
        if (root.dataset.step !== step) root.dataset.step = step;
      }, options),
    );
  };

  play();
  media.addEventListener("change", play);
}
