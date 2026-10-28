(() => {
  const place = (root) => {
    const mark = root.querySelector(".hero-mark");
    const spell = root.querySelector(".hero-spell");
    const text = mark && mark.firstChild;
    if (!mark || !spell || !text || text.nodeType !== Node.TEXT_NODE) return;
    const style = getComputedStyle(mark);
    const context = document.createElement("canvas").getContext("2d");
    if (!context) return;
    context.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const box = root.getBoundingClientRect();
    const range = document.createRange();
    const line = parseFloat(getComputedStyle(spell).fontSize) * 1.3;
    const edge = document.documentElement.clientWidth - box.left - 8;
    const rows = [];
    const spots = Array.from(spell.querySelectorAll("[data-at]"), (label) => {
      const at = Number(label.dataset.at);
      range.setStart(text, at);
      range.setEnd(text, at + 1);
      const glyph = range.getBoundingClientRect();
      const metrics = context.measureText(text.textContent.charAt(at));
      const half = label.getBoundingClientRect().width / 2;
      const center = Math.min(glyph.left + (metrics.actualBoundingBoxRight - metrics.actualBoundingBoxLeft) / 2 - box.left, edge - half);
      let row = 0;
      while (rows[row] !== undefined && rows[row] + 6 > center - half) row++;
      rows[row] = center + half;
      return { label, center, half, row, baseline: glyph.top + metrics.fontBoundingBoxAscent - box.top };
    });
    for (const spot of spots) {
      spot.label.style.setProperty("--x", `${spot.center.toFixed(1)}px`);
      spot.label.style.setProperty("--y", `${(spot.baseline + parseFloat(style.fontSize) * 0.08 + spot.row * line).toFixed(1)}px`);
    }
    spell.toggleAttribute("data-placed", spots.every((spot) => box.left + spot.center - spot.half >= 0));
  };

  for (const root of document.querySelectorAll("[data-spell]")) {
    const again = () => place(root);
    again();
    if (document.fonts) document.fonts.ready.then(again);
    new ResizeObserver(again).observe(root);
  }
})();
