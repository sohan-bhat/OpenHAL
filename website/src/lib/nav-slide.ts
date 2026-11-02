import { release, tween } from "./motion";

/** How long the highlight and the accent bar take to slide between sections, in seconds. */
export const SLIDE = 0.24;

/**
 * Slides the header's highlight and accent bar with Motion from the section a person left, where
 * nav-slide-start.ts put them before the first paint, to the current section. Both stay inside the
 * header under its labels, so the labels stay readable over the highlight the whole way.
 */
export function glide(): void {
  const nav = document.querySelector<HTMLElement>(".oh-sections[data-slide]");
  if (!nav) return;
  delete nav.dataset.slide;
  for (const part of nav.querySelectorAll<HTMLElement>(".nav-pill, .nav-mark")) {
    if (!part.style.transform) continue;
    const frames = part.matches(".nav-pill") ? { transform: [part.style.transform, "none"], borderRadius: [part.style.borderRadius, "6px"] } : { transform: [part.style.transform, "none"] };
    void tween(part, frames, SLIDE).finally(() => release(part, "transform", "border-radius"));
  }
}

addEventListener("oh:nav-slide", glide);
glide();
