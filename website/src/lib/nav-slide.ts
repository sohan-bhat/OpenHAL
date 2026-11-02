/** How long the highlight and the accent bar take to slide between sections, in seconds. */
export const SLIDE = 0.24;

/**
 * Slides the header's highlight and accent bar with Motion from the section a person left, where
 * nav-slide-start.ts put them before the first paint, to the current section. Both stay inside the
 * header under its labels, so the labels stay readable over the highlight the whole way. Motion
 * loads only for a slide.
 */
export function glide(): void {
  const nav = document.querySelector<HTMLElement>(".oh-sections[data-slide]");
  if (!nav) return;
  delete nav.dataset.slide;
  const parts = [...nav.querySelectorAll<HTMLElement>(".nav-pill, .nav-mark")].filter((part) => part.style.transform);
  void import("./motion").then(
    ({ release, tween }) => {
      for (const part of parts) {
        const frames = part.matches(".nav-pill") ? { transform: [part.style.transform, "none"], borderRadius: [part.style.borderRadius, "6px"] } : { transform: [part.style.transform, "none"] };
        void tween(part, frames, SLIDE).finally(() => release(part, "transform", "border-radius"));
      }
    },
    () => {
      for (const part of parts) for (const name of ["transform", "border-radius"]) part.style.removeProperty(name);
    },
  );
}

addEventListener("oh:nav-slide", glide);
glide();
