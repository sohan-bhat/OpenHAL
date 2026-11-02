const KEY = "openhal:nav-from";
const RADIUS = 6;
const INSET = 10;

/**
 * Runs inline right after the header's sections, before the page first paints. When a person
 * clicked another section on the page before, it puts the highlight and the accent bar back over
 * that section, so nav-slide.ts can move both with Motion to the current one.
 */
export function start(): void {
  let saved: { from?: number; to?: string; at?: number } | null = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
    sessionStorage.removeItem(KEY);
  } catch {}
  if (!saved || saved.to !== location.pathname || Date.now() - (saved.at ?? 0) > 10_000) return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const nav = document.querySelector<HTMLElement>(".oh-sections");
  if (!nav) return;
  const links = [...nav.querySelectorAll<HTMLElement>("a[data-match]")];
  const here = links.findIndex((link) => link.getAttribute("aria-current") === "page");
  const from = links[saved.from ?? -1];
  if (here < 0 || !from || saved.from === here) return;
  const pill = links[here].querySelector<HTMLElement>(".nav-pill");
  const mark = links[here].parentElement?.querySelector<HTMLElement>(".nav-mark");
  const was = from.getBoundingClientRect();
  const now = links[here].getBoundingClientRect();
  if (!pill || !mark || !now.width) return;
  const scale = was.width / now.width;
  pill.style.transform = `translateX(${was.left - now.left}px) scaleX(${scale})`;
  pill.style.borderRadius = `${RADIUS / scale}px / ${RADIUS}px`;
  mark.style.transform = `translateX(${was.left - now.left}px) scaleX(${(was.width - 2 * INSET) / (now.width - 2 * INSET)})`;
  nav.dataset.slide = "";
  dispatchEvent(new Event("oh:nav-slide"));
}

if ((document as Document & { prerendering?: boolean }).prerendering) addEventListener("prerenderingchange", start, { once: true });
else start();
