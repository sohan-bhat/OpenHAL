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
    const spots = Array.from(spell.querySelectorAll("[data-at]"), (label) => {
      const at = Number(label.dataset.at);
      range.setStart(text, at);
      range.setEnd(text, at + 1);
      const glyph = range.getBoundingClientRect();
      const metrics = context.measureText(text.textContent.charAt(at));
      const center = glyph.left + (metrics.actualBoundingBoxRight - metrics.actualBoundingBoxLeft) / 2 - box.left;
      const baseline = glyph.top + metrics.fontBoundingBoxAscent - box.top;
      return { label, center, half: label.getBoundingClientRect().width / 2, baseline };
    });
    for (let pass = 0; pass < spots.length; pass++) {
      for (let index = 1; index < spots.length; index++) {
        const left = spots[index - 1];
        const right = spots[index];
        const overlap = left.center + left.half + 6 - (right.center - right.half);
        if (overlap > 0) {
          left.center -= overlap / 2;
          right.center += overlap / 2;
        }
      }
    }
    const last = spots[spots.length - 1];
    const over = last ? last.center + last.half - (document.documentElement.clientWidth - box.left - 8) : 0;
    for (const spot of spots) {
      spot.label.style.setProperty("--x", `${(spot.center - Math.max(0, over)).toFixed(1)}px`);
      spot.label.style.setProperty("--y", `${(spot.baseline + parseFloat(style.fontSize) * 0.08).toFixed(1)}px`);
    }
    const boxes = Array.from(spell.children, (label) => label.getBoundingClientRect());
    const apart = boxes.every((item, index) => index === 0 || item.left >= boxes[index - 1].right + 4);
    spell.toggleAttribute("data-placed", apart && boxes.every((item) => item.left >= 0));
  };

  for (const root of document.querySelectorAll("[data-spell]")) {
    const again = () => place(root);
    again();
    if (document.fonts) document.fonts.ready.then(again);
    new ResizeObserver(again).observe(root);
  }
})();
