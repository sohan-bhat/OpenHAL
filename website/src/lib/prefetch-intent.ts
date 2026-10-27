import { prefetch } from "astro/virtual-modules/prefetch.js";

const SKIP = /\/(?:pagefind|captures|og)\//;

function wanted(event: Event): string | null {
  const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
  if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download") || /\bexternal\b/.test(link.rel)) return null;
  const url = new URL(link.href, window.location.href);
  if (url.origin !== window.location.origin || SKIP.test(url.pathname)) return null;
  if (url.pathname === window.location.pathname && url.search === window.location.search) return null;
  return url.href;
}

/**
 * Fetches a page ahead for browsers without speculation rules, with Astro's prefetch, when a person
 * points at a link for a moment, presses on it or tabs to it. The page's own scripts and the
 * Playground's kernel are not fetched, only the HTML.
 */
export function prefetchOnIntent(): void {
  let timer = 0;
  const later = (event: Event) => {
    const href = wanted(event);
    window.clearTimeout(timer);
    if (href) timer = window.setTimeout(() => prefetch(href), 80);
  };
  const now = (event: Event) => {
    const href = wanted(event);
    if (href) prefetch(href, { ignoreSlowConnection: true });
  };
  document.addEventListener("pointerover", later, { passive: true });
  document.addEventListener("focusin", later, { passive: true });
  document.addEventListener("pointerout", () => window.clearTimeout(timer), { passive: true });
  document.addEventListener("pointerdown", now, { passive: true });
  document.addEventListener("touchstart", now, { passive: true });
}
