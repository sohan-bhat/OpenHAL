import { scrollInfo } from "motion";
import { animate } from "motion/mini";
import { CAMERA } from "../../lib/story/camera";

type Kind = "line" | "dash" | "show" | "hide" | "pass";

/** What each kind of piece does as it plays, from its first value to its last. */
const FRAMES: Record<Kind, Record<string, [string | number, string | number]>> = {
  line: { transform: ["scaleX(0)", "scaleX(1)"] },
  dash: { clipPath: ["inset(0 0 0 100%)", "inset(0 0 0 0%)"] },
  show: { opacity: [0, 1] },
  hide: { opacity: [1, 0] },
  pass: { opacity: [0, 1] },
};

/**
 * Plays How it works with the scroll. The stage pins under the header while the page scrolls past
 * the track, and Motion's scrollInfo() turns the scroll through the track into one progress, from the
 * moment the stage pins under the header to the moment it lets go. Every piece is a paused Motion
 * animation one second long, set to that progress on each frame, so an arrow draws as the page
 * scrolls and scrolling back plays it in reverse. Each piece names its kind and the stretch of the
 * scroll it changes in, `data-draw="line 0.04 0.0733"`, and a value that shows and then hides
 * names both stretches, `data-draw="pass 0.88 0.01 0.95 0.01"`. The step count and the step on show
 * follow the same progress. The stage pins at the header's measured height. Once the last step
 * has played, the content after the section slides up over the pinned stage, so no line of the
 * stage passes under the header, and the stage hides once the content covers the stage. With
 * reduced motion, on a screen too short for the stage, or before this runs, the steps are three
 * still panels.
 */
export function howItWorks(root: HTMLElement): void {
  const track = root.querySelector<HTMLElement>(".how-track");
  const run = root.querySelector<HTMLElement>(".how-run");
  const stage = root.querySelector<HTMLElement>(".how-stage");
  const count = Number(root.dataset.count) || 1;
  const media = window.matchMedia(CAMERA);
  let stop: (() => void) | null = null;
  let played: Array<ReturnType<typeof animate>> = [];

  const still = () => {
    stop?.();
    stop = null;
    for (const animation of played) animation.cancel();
    played = [];
    root.removeAttribute("data-motion");
    root.removeAttribute("data-step");
    root.removeAttribute("data-past");
  };

  const play = () => {
    still();
    if (!track || !run || !stage || !media.matches) return;
    const pin = document.querySelector<HTMLElement>("header.header")?.offsetHeight ?? 0;
    root.style.setProperty("--how-pin", `${pin}px`);
    root.setAttribute("data-motion", "");
    root.setAttribute("data-step", "1");
    if (stage.scrollHeight > stage.clientHeight + 1) return still();
    for (const piece of root.querySelectorAll<HTMLElement>("[data-draw]")) {
      const [kind, ...numbers] = (piece.dataset.draw ?? "").split(" ");
      const frames = FRAMES[kind as Kind];
      if (!frames) continue;
      const [start, length, end, fade] = numbers.map(Number);
      const from = start;
      const to = Math.min(1, from + length);
      const both = kind === "pass";
      const times = both ? [0, from, to, end, Math.min(1, end + fade), 1] : [0, from, to, 1];
      const keyframes = Object.fromEntries(Object.entries(frames).map(([name, [first, last]]) => [name, both ? [first, first, last, last, first, first] : [first, first, last, last]]));
      played.push(animate(piece, keyframes, { duration: 1, ease: "linear", times, autoplay: false }));
    }
    const offset: [`start ${number}px`, "end end"] = [`start ${pin}px`, "end end"];
    stop = scrollInfo(
      ({ y }) => {
        const progress = Math.min(1, Math.max(0, y.progress));
        for (const animation of played) animation.time = progress;
        const step = String(Math.min(count, Math.floor(progress * count) + 1));
        if (root.dataset.step !== step) root.dataset.step = step;
        const past = y.current - (y.offset[y.offset.length - 1] ?? 0) >= stage.offsetHeight;
        if (past !== root.hasAttribute("data-past")) root.toggleAttribute("data-past", past);
      },
      { target: run, offset },
    );
  };

  play();
  media.addEventListener("change", play);
}
