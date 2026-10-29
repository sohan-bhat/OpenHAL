import { frames } from "./walk";

/**
 * Wires the walkthrough's Previous and Next buttons. Next plays the next step's arrows along their
 * lifelines with Motion, about a second for a step, and Previous goes back to the end of the step
 * before at once. With reduced motion every step shows at once. The button at either end stays
 * focusable and says it can't go further, and a live region reads each step's caption.
 */
export function walkthrough(root: HTMLElement): void {
  const stops = (root.dataset.stops ?? "").split(" ").filter(Boolean).map(Number);
  const previous = root.querySelector<HTMLButtonElement>("[data-previous]");
  const next = root.querySelector<HTMLButtonElement>("[data-next]");
  const said = root.querySelector<HTMLElement>("[data-said]");
  const notes = Array.from(root.querySelectorAll<HTMLElement>(".story-note"));
  if (!previous || !next || stops.length === 0) return;
  const draw = frames(root);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  let index = 0;
  let time = stops[0];
  let playing: { stop: () => void } | null = null;

  const settle = (announce: boolean) => {
    previous.setAttribute("aria-disabled", String(index === 0));
    next.setAttribute("aria-disabled", String(index === stops.length - 1));
    if (announce && said) said.textContent = notes[index]?.textContent?.replace(/\s+/g, " ").trim() ?? "";
  };

  const go = async (to: number) => {
    if (to < 0 || to >= stops.length || to === index) return;
    const target = stops[to];
    index = to;
    playing?.stop();
    playing = null;
    settle(true);
    if (reduce.matches || target < time) {
      time = target;
      draw(time);
      return;
    }
    try {
      const { tween } = await import("./tween");
      if (index !== to) return;
      playing = tween(time, target, Math.min(1.2, 0.02 * (target - time)), (value) => {
        time = value;
        draw(value);
      });
    } catch {
      time = target;
      draw(time);
    }
  };

  previous.addEventListener("click", () => go(index - 1));
  next.addEventListener("click", () => go(index + 1));
  draw(time);
  settle(false);
}
