import type { ClientDirective } from "astro";

const STARTERS = ["pointerover", "pointerdown", "focusin", "touchstart", "input"];
const HELD = ["click", "keydown"];
const OPENERS = new Set(["Enter", " ", "ArrowDown", "ArrowUp"]);
const READY = "oh:island-ready";

function copy(event: Event): Event {
  if (event instanceof KeyboardEvent) {
    const { key, code, metaKey, ctrlKey, shiftKey, altKey } = event;
    return new KeyboardEvent("keydown", { key, code, metaKey, ctrlKey, shiftKey, altKey, bubbles: true, cancelable: true });
  }
  const { clientX, clientY, button, detail, metaKey, ctrlKey, shiftKey, altKey } = event as MouseEvent;
  return new MouseEvent("click", { clientX, clientY, button, detail, metaKey, ctrlKey, shiftKey, altKey, bubbles: true, cancelable: true, composed: true, view: window });
}

/**
 * Hydrates an island of form controls, such as the catalog filters, at once
 * when the address carries one of the query fields the directive's value names, such as
 * client:query="q tier hazard", so a shared filtered view shows its choices, and otherwise on the
 * first sign that a person means to use a control: the pointer over the island, a label included,
 * focus, a touch or typing. A press on a button, a label's click included, or an opening key on a
 * select that arrives while the island loads is held and replayed once the island is ready, and
 * text typed meanwhile stays in its field for the island to read.
 */
const query: ClientDirective = (load, options, element) => {
  const fields = typeof options.value === "string" ? options.value.split(/\s+/).filter(Boolean) : [];
  const held: Array<{ target: EventTarget; event: Event }> = [];
  let started = false;

  const hold = (event: Event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const control = target.closest("button");
    if (!control) return;
    if (event instanceof KeyboardEvent && !(OPENERS.has(event.key) && control.matches("[role=combobox]"))) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    held.push({ target: control, event: copy(event) });
  };

  async function start(): Promise<void> {
    if (started) return;
    started = true;
    for (const name of STARTERS) element.removeEventListener(name, start, true);
    for (const name of HELD) element.addEventListener(name, hold, true);
    const ready = new Promise<void>((resolve) => {
      const done = () => resolve();
      element.addEventListener(READY, done, { once: true });
      window.setTimeout(done, 3000);
    });
    try {
      const hydrate = await load();
      await hydrate();
      await ready;
    } finally {
      for (const name of HELD) element.removeEventListener(name, hold, true);
    }
    for (const { target, event } of held.splice(0)) {
      if (target instanceof Node && target.isConnected) target.dispatchEvent(event);
    }
  }

  const params = new URLSearchParams(window.location.search);
  if (fields.some((field) => params.get(field)?.trim())) {
    void start();
    return;
  }
  for (const name of STARTERS) element.addEventListener(name, start, { capture: true, passive: true });
};

export default query;
