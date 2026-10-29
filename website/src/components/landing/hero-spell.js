(() => {
  const GAP = 8;

  const spread = (spots, low, high) => {
    const count = spots.length;
    const need = spots.slice(1).map((spot, index) => spots[index].half + spot.half + GAP);
    const lowest = spots.map((spot) => Math.max(spot.ink[0], low + spot.half));
    const highest = spots.map((spot) => Math.min(spot.ink[1], high - spot.half));
    const fit = (reach) => {
      const room = spots.map((spot, index) => [Math.max(lowest[index], spot.center - reach), Math.min(highest[index], spot.center + reach)]);
      const left = [];
      for (let index = 0; index < count; index++) {
        left[index] = index ? Math.max(room[index][0], left[index - 1] + need[index - 1]) : room[index][0];
        if (left[index] > room[index][1] + 0.01) return null;
      }
      const right = [];
      for (let index = count - 1; index >= 0; index--) right[index] = index < count - 1 ? Math.min(room[index][1], right[index + 1] - need[index]) : room[index][1];
      return left.map((value, index) => (value + right[index]) / 2);
    };
    if (!fit(1000)) return null;
    let [near, far] = [0, 1000];
    for (let pass = 0; pass < 24 && far - near > 0.05; pass++) {
      const middle = (near + far) / 2;
      if (fit(middle)) far = middle;
      else near = middle;
    }
    return fit(far);
  };

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
      const origin = glyph.left - box.left;
      const ink = [origin - metrics.actualBoundingBoxLeft, origin + metrics.actualBoundingBoxRight];
      return { label, ink, center: (ink[0] + ink[1]) / 2, half: label.getBoundingClientRect().width / 2, baseline: glyph.top + metrics.fontBoundingBoxAscent - box.top };
    });
    const placed = spread(spots, 8 - box.left, document.documentElement.clientWidth - box.left - 8);
    const line = parseFloat(getComputedStyle(spell).fontSize) * 1.3;
    spots.forEach((spot, index) => {
      const row = placed ? 0 : index % 2;
      spot.label.style.setProperty("--x", `${(placed ? placed[index] : spot.center).toFixed(1)}px`);
      spot.label.style.setProperty("--y", `${(spot.baseline + parseFloat(style.fontSize) * 0.08 + row * line).toFixed(1)}px`);
    });
    spell.toggleAttribute("data-placed", true);
  };

  for (const root of document.querySelectorAll("[data-spell]")) {
    const again = () => place(root);
    again();
    if (document.fonts) document.fonts.ready.then(again);
    new ResizeObserver(again).observe(root);
  }
})();
