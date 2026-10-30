/**
 * Draws the example's sequence diagram at one moment of the story. Every piece that lists spans of
 * story time in data-in carries data-on while the time is inside one of them, and every piece with
 * an inline --at and --d reads the time as --t, held to the stretch in which the piece changes, so
 * story.css draws its line that far. The page runs this inline before its first paint, so the
 * diagram opens on the first step, and again from the walkthrough's buttons. This file imports
 * nothing for that reason.
 */
export function frames(root: HTMLElement): (t: number) => void {
  const states = Array.from(root.querySelectorAll<HTMLElement>("[data-in]"), (el) => ({
    el,
    spans: (el.dataset.in ?? "").split(" ").filter(Boolean).map(Number),
    on: el.hasAttribute("data-on"),
  }));
  const pieces = Array.from(root.querySelectorAll<HTMLElement>('[style*="--at:"]'), (el) => {
    const at = parseFloat(el.style.getPropertyValue("--at")) || 0;
    return { el, from: at - 1, to: at + (parseFloat(el.style.getPropertyValue("--d")) || 0) + 1, last: "" };
  });
  return (t: number) => {
    for (const state of states) {
      let now = false;
      for (let index = 0; index < state.spans.length; index += 2) if (t >= state.spans[index] && t < state.spans[index + 1]) now = true;
      if (now !== state.on) state.el.toggleAttribute("data-on", (state.on = now));
    }
    for (const piece of pieces) {
      const value = Math.min(piece.to, Math.max(piece.from, t)).toFixed(2);
      if (value !== piece.last) piece.el.style.setProperty("--t", (piece.last = value));
    }
  };
}
