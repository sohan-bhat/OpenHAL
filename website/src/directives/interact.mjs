const STARTERS = ["pointerdown", "focusin", "keydown", "touchstart", "input", "change"];
const HELD = ["click", "submit"];
const VALUES = ["input", "change"];

export default (load, _options, element) => {
  let started = false;
  const held = [];
  const values = new Map();
  const hold = (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    held.push(event);
  };
  const remember = (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement)) return;
    values.delete(target);
    values.set(target, { type: event.type, value: target.value });
  };
  const start = async (event) => {
    if (event && VALUES.includes(event.type)) remember(event);
    if (started) return;
    started = true;
    for (const name of STARTERS) element.removeEventListener(name, start, true);
    for (const name of HELD) element.addEventListener(name, hold, true);
    for (const name of VALUES) element.addEventListener(name, remember, true);
    try {
      const hydrate = await load();
      await hydrate();
    } finally {
      for (const name of HELD) element.removeEventListener(name, hold, true);
      for (const name of VALUES) element.removeEventListener(name, remember, true);
    }
    for (const [target, { type, value }] of values) {
      target.value = value;
      target.dispatchEvent(new Event(type, { bubbles: true }));
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
