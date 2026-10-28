import { measure, place, settle, type Opening } from "./opening";
import type { Scene } from "./scene-runtime";

/** Where the word's baseline sits in its line box, and how far its ink reaches below the baseline. */
function ink(letters: HTMLElement): { baseline: number; descent: number } {
  const height = letters.offsetHeight;
  const style = getComputedStyle(letters);
  const context = document.createElement("canvas").getContext("2d");
  if (!context) return { baseline: height * 0.84, descent: height * 0.2 };
  context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const metrics = context.measureText(letters.textContent ?? "");
  return { baseline: (height - metrics.fontBoundingBoxAscent - metrics.fontBoundingBoxDescent) / 2 + metrics.fontBoundingBoxAscent, descent: metrics.actualBoundingBoxDescent };
}

/**
 * Measures where the wordmark comes down to and where each brief sits, from the letters
 * themselves. The word stays where it stands in the column, and the word and the tallest brief are
 * centred in the stage together. On a wide screen each brief starts right under its own letter's
 * baseline, as far as the column allows, and on a narrow one the brief sits under the whole word,
 * clear of the p's descender. The results are custom properties the stylesheet reads with the
 * story time. The scene also carries the demo's opening, which drops away on the first scroll.
 */
export function wordmark(root: HTMLElement): Pick<Scene, "layout" | "play" | "rest"> {
  const stage = root.querySelector<HTMLElement>(".hero-stage");
  const name = root.querySelector<HTMLElement>(".hero-name");
  const letters = root.querySelector<HTMLElement>(".hero-letters");
  const briefs = Array.from(root.querySelectorAll<HTMLElement>(".hero-brief"));
  const wide = window.matchMedia("(min-width: 1024px)");
  const set = (el: HTMLElement, property: string, value: number) => el.style.setProperty(property, `${Math.round(value)}px`);
  let opening: Opening | null = null;
  return {
    layout: () => {
      if (!stage || !name || !letters) return;
      const { baseline, descent } = ink(letters);
      const reach = baseline + (wide.matches ? 0 : descent) + parseFloat(getComputedStyle(letters).fontSize) * 0.1 + 8;
      const tallest = Math.max(0, ...briefs.map((brief) => brief.offsetHeight));
      const top = Math.max(name.offsetTop, (stage.clientHeight - reach - tallest) / 2);
      set(root, "--down", top - name.offsetTop);
      set(root, "--brief-top", top + reach);
      for (const brief of briefs) {
        const letter = letters.querySelector<HTMLElement>(`[data-letter="${brief.dataset.letter}"]`);
        const left = name.offsetLeft + letters.offsetLeft + (letter?.offsetLeft ?? 0);
        set(brief, "--anchor", Math.max(0, Math.min(left, stage.clientWidth - brief.offsetWidth)));
      }
      opening = measure(root);
    },
    play: (t, y) => {
      if (opening) place(opening, t, y);
    },
    rest: () => {
      if (opening) settle(opening);
      opening = null;
    },
  };
}
