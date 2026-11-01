const KEYS = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"]);

function canScroll(element: Element, dx: number, dy: number): boolean {
  const style = getComputedStyle(element);
  if (dy !== 0 && /(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight) {
    if (dy < 0 ? element.scrollTop > 0 : element.scrollTop + element.clientHeight < element.scrollHeight - 1) return true;
  }
  if (dx !== 0 && /(auto|scroll)/.test(style.overflowX) && element.scrollWidth > element.clientWidth) {
    if (dx < 0 ? element.scrollLeft > 0 : element.scrollLeft + element.clientWidth < element.scrollWidth - 1) return true;
  }
  return false;
}

function scrollsInside(target: EventTarget | null, boundary: Element, dx: number, dy: number): boolean {
  let element = target instanceof Element ? target : null;
  while (element) {
    if (canScroll(element, dx, dy)) return true;
    if (element === boundary) return false;
    element = element.parentElement;
  }
  return false;
}

function editable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || target.matches("input, textarea, select, [role='slider']"));
}

/**
 * Keeps the page behind an open modal from scrolling while the page's scrollbar stays in place.
 * The wheel, touch and scrolling keys still scroll any scrollable area inside the node.
 */
export function holdPageScroll(node: HTMLElement): () => void {
  let x = 0;
  let y = 0;
  const wheel = (event: WheelEvent) => {
    if (!scrollsInside(event.target, node, event.deltaX, event.deltaY)) event.preventDefault();
  };
  const touchstart = (event: TouchEvent) => {
    const touch = event.touches[0];
    if (!touch) return;
    x = touch.clientX;
    y = touch.clientY;
  };
  const touchmove = (event: TouchEvent) => {
    const touch = event.touches[0];
    if (!touch) return;
    const dx = x - touch.clientX;
    const dy = y - touch.clientY;
    x = touch.clientX;
    y = touch.clientY;
    if (!scrollsInside(event.target, node, dx, dy)) event.preventDefault();
  };
  const keydown = (event: KeyboardEvent) => {
    if (!KEYS.has(event.key) || editable(event.target)) return;
    const dy = event.key === "ArrowUp" || event.key === "PageUp" || event.key === "Home" ? -1 : 1;
    if (!scrollsInside(event.target, node, 0, dy)) event.preventDefault();
  };
  node.addEventListener("wheel", wheel, { passive: false });
  node.addEventListener("touchstart", touchstart, { passive: true });
  node.addEventListener("touchmove", touchmove, { passive: false });
  node.addEventListener("keydown", keydown);
  return () => {
    node.removeEventListener("wheel", wheel);
    node.removeEventListener("touchstart", touchstart);
    node.removeEventListener("touchmove", touchmove);
    node.removeEventListener("keydown", keydown);
  };
}
