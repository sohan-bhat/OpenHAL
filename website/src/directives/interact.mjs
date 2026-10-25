const STARTERS = ["pointerdown", "focusin", "keydown", "touchstart"];
const HELD = ["click", "submit"];

export default (load, _options, element) => {
  let started = false;
  const held = [];
  const hold = (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    held.push(event);
  };
  const start = async () => {
    if (started) return;
    started = true;
    for (const name of STARTERS) element.removeEventListener(name, start, true);
    for (const name of HELD) element.addEventListener(name, hold, true);
    try {
      const hydrate = await load();
      await hydrate();
    } finally {
      for (const name of HELD) element.removeEventListener(name, hold, true);
    }
    for (const event of held) {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) continue;
      if (event.type === "submit" && target instanceof HTMLFormElement) target.requestSubmit();
      else if (event.type === "click") (target.closest("button, a, input, label, summary") ?? target).click();
    }
  };
  if (new URLSearchParams(window.location.search).has("example")) {
    start();
    return;
  }
  for (const name of STARTERS) element.addEventListener(name, start, { capture: true, passive: true });
};
