const EASE = 9;

function scrollsItself(target: EventTarget | null, delta: number): boolean {
  for (let el = target instanceof Element ? target : null; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
    if (el instanceof HTMLDialogElement && el.open) return true;
    const { overflowY } = getComputedStyle(el);
    if ((overflowY === "auto" || overflowY === "scroll") && el.scrollHeight > el.clientHeight) {
      if (delta < 0 ? el.scrollTop > 0 : el.scrollTop + el.clientHeight < el.scrollHeight) return true;
    }
  }
  return false;
}

/**
 * Eases wheel and trackpad scrolling of the page. Each wheel event moves a target by the person's
 * own distance, and the page glides toward it with the native scroll. The glide keeps its own
 * position in fractions of a pixel, since the browser rounds the scroll to whole device pixels, so
 * the glide always reaches its target and a scroll up past the top lands at 0. Anything else that
 * scrolls the page, the scrollbar, the keyboard, an anchor link, find in page or a touch, takes
 * over at once, since the glide stops the moment the page is not where it left it. Returns a
 * function that turns it off.
 */
export function smooth(): () => void {
  let target = window.scrollY;
  let placed = window.scrollY;
  let frame = 0;
  let last = 0;

  const limit = () => document.documentElement.scrollHeight - window.innerHeight;

  const step = (now: number) => {
    if (Math.abs(window.scrollY - placed) > 1.5) {
      frame = 0;
      return;
    }
    const dt = Math.min(0.05, Math.max(0, (now - last) / 1000)) || 1 / 60;
    last = now;
    const next = placed + (target - placed) * (1 - Math.exp(-EASE * dt));
    placed = Math.abs(target - next) < 0.5 ? target : next;
    window.scrollTo({ top: placed, behavior: "instant" });
    frame = placed === target ? 0 : requestAnimationFrame(step);
  };

  const wheel = (event: WheelEvent) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaMode === 2 ? event.deltaY * window.innerHeight : event.deltaY;
    if (!delta || scrollsItself(event.target, delta)) return;
    event.preventDefault();
    if (!frame) {
      target = placed = window.scrollY;
      last = performance.now();
      frame = requestAnimationFrame(step);
    }
    target = Math.max(0, Math.min(limit(), target + delta));
  };

  window.addEventListener("wheel", wheel, { passive: false });
  return () => {
    window.removeEventListener("wheel", wheel);
    cancelAnimationFrame(frame);
    frame = 0;
  };
}
