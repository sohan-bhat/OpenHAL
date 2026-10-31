import { CLOSE, OPEN, release, still, tween } from "./motion";

const WIDE = "(min-width: 50rem)";

/**
 * The parts of a page that move over when the sidebar hides or shows, each with the element whose
 * place says how far it moves: the content, measured by its column, and the outline beside it or
 * above it.
 */
function movers(): Array<[HTMLElement, HTMLElement]> {
  const pairs: Array<[HTMLElement | null, HTMLElement | null]> = [[document.querySelector("main"), document.querySelector<HTMLElement>("main .sl-container")]];
  for (const element of document.querySelectorAll<HTMLElement>(".right-sidebar, mobile-starlight-toc nav")) pairs.push([element, element]);
  return pairs.filter((pair): pair is [HTMLElement, HTMLElement] => Boolean(pair[0] && pair[1]?.getClientRects().length));
}

/**
 * Hides or shows the sidebar for a person's toggle, whichever control the person used. Marks the
 * root, so the stylesheet gives the content and the outline the space the sidebar leaves or takes
 * and every part that follows the root hides or shows, and moves the content and the outline over
 * from where they stood with Motion while the sidebar slides, using transforms only. A part moving
 * already starts again from where it is.
 */
export function moveOver(open: boolean): void {
  const root = document.documentElement;
  if ((root.dataset.sidebar !== "collapsed") === open) return;
  const moving = matchMedia(WIDE).matches && !still();
  const before = moving ? movers().map(([mover, probe]) => [mover, probe, probe.getBoundingClientRect().left] as const) : [];
  for (const [mover] of before) {
    for (const animation of mover.getAnimations()) animation.cancel();
    release(mover, "transform");
  }
  if (open) delete root.dataset.sidebar;
  else root.dataset.sidebar = "collapsed";
  const shifts = before.map(([mover, probe, left]) => [mover, left - probe.getBoundingClientRect().left] as const);
  for (const [mover, shift] of shifts) {
    if (Math.abs(shift) < 0.5) continue;
    const from = `translateX(${shift}px)`;
    mover.style.transform = from;
    tween(mover, { transform: [from, "translateX(0px)"] }, open ? OPEN : CLOSE).then(
      () => release(mover, "transform"),
      () => {},
    );
  }
}
