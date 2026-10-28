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
 * Measures where the wordmark comes down to, how far it slides and where the briefs sit, from the
 * letters themselves. Coming down, the word moves right until H stands where L stands at rest, and
 * between letters the whole word slides left so A and then L land on that same spot, which leaves
 * the word at rest under L. Where the moved word would pass the column's right edge, on phones and
 * narrow tablets, the word also shrinks while it comes down, just enough to fit, so no letter is
 * ever cut off. The word and the tallest brief are centred in the stage together. On a wide screen
 * every brief starts under the spot where the current letter lands, as far as the column allows,
 * and on a narrow one the brief sits under the whole word, clear of the p's descender. The results
 * are custom properties the stylesheet reads with the story time. The scene also carries the
 * demo's opening, which drops away on the first scroll.
 */
export function wordmark(root: HTMLElement): Pick<Scene, "layout" | "play" | "rest"> {
  const stage = root.querySelector<HTMLElement>(".hero-stage");
  const name = root.querySelector<HTMLElement>(".hero-name");
  const letters = root.querySelector<HTMLElement>(".hero-letters");
  const briefs = Array.from(root.querySelectorAll<HTMLElement>(".hero-brief"));
  const wide = window.matchMedia("(min-width: 1024px)");
  const set = (el: HTMLElement, property: string, value: number) => el.style.setProperty(property, `${value.toFixed(2)}px`);
  let opening: Opening | null = null;
  return {
    layout: () => {
      if (!stage || !name || !letters) return;
      const left = (letter: string) => letters.querySelector<HTMLElement>(`[data-letter="${letter}"]`)?.offsetLeft ?? 0;
      const [h, a, l] = [left("H"), left("A"), left("L")];
      const start = name.offsetLeft + letters.offsetLeft;
      const scale = Math.min(1, (stage.clientWidth - start - 2) / (letters.offsetWidth + l - h));
      root.style.setProperty("--scale", scale.toFixed(4));
      set(root, "--shift-h", scale * (l - h));
      set(root, "--shift-a", scale * (l - a));
      const { baseline, descent } = ink(letters);
      const reach = scale * (baseline + (wide.matches ? 0 : descent) + parseFloat(getComputedStyle(letters).fontSize) * 0.1) + 8;
      const tallest = Math.max(0, ...briefs.map((brief) => brief.offsetHeight));
      const top = Math.max(name.offsetTop, (stage.clientHeight - reach - tallest) / 2);
      set(root, "--down", top - name.offsetTop);
      set(root, "--brief-top", top + reach);
      for (const brief of briefs) set(brief, "--anchor", Math.max(0, Math.min(start + scale * l, stage.clientWidth - brief.offsetWidth)));
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
