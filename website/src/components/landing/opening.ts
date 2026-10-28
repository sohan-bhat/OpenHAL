/**
 * The demo's opening on the first screen. While the hero sits at the top, the story's own stage is
 * lifted by a transform into the slot under the hero and clipped to the step count's row, and to
 * the story's title where the title fits, so the step count, Skip the demo and the Smooth scrolling
 * switch are the real ones and work from the first screen. Only properties that no child inherits
 * change, so lifting and settling restyle the stage alone. The first scroll drops
 * the opening away with the hero's small diagram, and once the drop is over the stage is back in
 * its own place far below, so the story arrives there after the wordmark sequence as before. Every
 * position is a function of the scroll, so scrolling back to the top puts the first screen back
 * exactly as it loaded. This file imports nothing, because the page also runs it inline to place
 * the opening before the first paint.
 */

export interface Opening {
  story: HTMLElement;
  stage: HTMLElement;
  /** The slot's top in the viewport while the hero's stage is pinned. */
  at: number;
  /** The story stage's own top in the page. */
  top: number;
  /** How far the opening drops while the story time goes from 0 to `drop`. */
  fall: number;
  drop: number;
  /** Whether the story's title shows under the step count, which needs the small diagram beside the hero and room under it. */
  title: boolean;
  /** How much of the stage shows from its top while it is lifted, the step count's row and the title where the title shows. */
  keep: number;
  /** What the stage shows now, which a fresh measurement does not know, so its first placement always writes. */
  last: string | null;
}

function pageTop(el: HTMLElement): number {
  let y = 0;
  for (let node: HTMLElement | null = el; node; node = node.offsetParent as HTMLElement | null) y += node.offsetTop;
  return y;
}

/** Measures where the opening sits, or returns null when the hero does not play. */
export function measure(hero: HTMLElement): Opening | null {
  const story = document.querySelector<HTMLElement>("[data-story]");
  const stage = story?.querySelector<HTMLElement>(".story-stage");
  const slot = hero.querySelector<HTMLElement>(".hero-slot");
  const demo = hero.querySelector<HTMLElement>(".hero-demo");
  const heads = story?.querySelector<HTMLElement>(".story-heads");
  const meta = story?.querySelector<HTMLElement>(".story-meta");
  if (!story || !stage || !slot || !demo || !heads || !meta || !hero.hasAttribute("data-camera")) return null;
  const pin = document.querySelector<HTMLElement>(".site-header")?.offsetHeight ?? 0;
  const view = document.querySelector<HTMLElement>(".story-probe")?.offsetHeight || window.innerHeight;
  const at = pin + slot.offsetTop;
  const top = stage.getBoundingClientRect().top;
  const below = heads.getBoundingClientRect().bottom - top;
  const title = demo.offsetTop < slot.offsetTop && at + below <= view - 8;
  return {
    story,
    stage,
    at,
    top: pageTop(stage),
    fall: view * (parseFloat(hero.style.getPropertyValue("--fall")) || 0),
    drop: parseFloat(hero.style.getPropertyValue("--drop")) || 1,
    title,
    keep: Math.ceil((title ? below : meta.getBoundingClientRect().bottom - top) + 8),
    last: null,
  };
}

/** Places the opening for story time t at scroll position y. */
export function place(opening: Opening, t: number, y: number): void {
  const gone = Math.min(1, Math.max(0, t / opening.drop));
  const lifted = gone < 1;
  const lift = opening.at + opening.fall * gone * (0.6 + 0.4 * gone) - (opening.top - y);
  const key = lifted ? `${lift.toFixed(1)} ${gone.toFixed(3)}` : "";
  if (key === opening.last) return;
  opening.last = key;
  opening.stage.style.transform = lifted ? `translate3d(0, ${lift.toFixed(1)}px, 0)` : "";
  opening.stage.style.opacity = lifted ? String(Math.min(0.999, 1 - gone)) : "";
  opening.stage.style.clipPath = lifted ? `inset(0 0 calc(100% - ${opening.keep}px) 0)` : "";
  if (lifted) opening.story.setAttribute("data-lifted", opening.title ? "title" : "band");
  else opening.story.removeAttribute("data-lifted");
}

/** Puts the story's stage back in its own place. */
export function settle(opening: Opening): void {
  opening.last = "";
  opening.stage.style.transform = "";
  opening.stage.style.opacity = "";
  opening.stage.style.clipPath = "";
  opening.story.removeAttribute("data-lifted");
}
