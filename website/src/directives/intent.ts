import type { ClientDirective } from "astro";

const STARTERS = ["pointerover", "pointerdown", "focusin", "touchstart"];
const HELD = ["pointerdown", "click", "keydown"];
const OPENERS = new Set(["Enter", " ", "ArrowDown", "ArrowUp"]);
const READY = "oh:island-ready";
const ANYWHERE = new Set(["mod+k"]);

/** True when an event comes from a field a person types in. */
export function isEditable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || /^(input|textarea|select)$/i.test(target.tagName));
}

/**
 * True when a key event is the island's shortcut, written like "mod+k" for Command or Control and
 * K. Only the search shortcut works while a person types in a field, so a field keeps its own keys.
 */
export function isShortcut(shortcut: string, event: KeyboardEvent): boolean {
  if (!shortcut || event.altKey || event.shiftKey || !(event.metaKey || event.ctrlKey)) return false;
  if (!ANYWHERE.has(shortcut) && isEditable(event.target)) return false;
  return event.key.toLowerCase() === shortcut.split("+").pop();
}

function copy(event: Event): Event {
  if (event instanceof KeyboardEvent) {
    const { key, code, metaKey, ctrlKey, shiftKey, altKey } = event;
    return new KeyboardEvent("keydown", { key, code, metaKey, ctrlKey, shiftKey, altKey, bubbles: true, cancelable: true });
  }
  const { clientX, clientY, button, buttons, detail, metaKey, ctrlKey, shiftKey, altKey } = event as MouseEvent;
  const init = { clientX, clientY, button, buttons, detail, metaKey, ctrlKey, shiftKey, altKey, bubbles: true, cancelable: true, composed: true, view: window };
  if (event.type === "pointerdown") return new PointerEvent("pointerdown", { ...init, pointerType: (event as PointerEvent).pointerType || "mouse", isPrimary: true });
  return new MouseEvent("click", init);
}

/**
 * Hydrates an island on the first sign that a person means to use it: the pointer over it, focus
 * inside it, a touch or a press, or its keyboard shortcut anywhere on the page, given as the
 * directive's value, such as client:intent="mod+k". Presses and the shortcut that arrive while
 * the island loads are held, then replayed once the island says it is ready, so the first click or
 * key still does what it should.
 */
const intent: ClientDirective = (load, options, element) => {
  const shortcut = typeof options.value === "string" ? options.value : "";
  const held: Array<{ target: EventTarget; event: Event }> = [];
  let started = false;

  const hold = (event: Event) => {
    const target = event.target;
    if (!target) return;
    if (event instanceof KeyboardEvent && !(OPENERS.has(event.key) && target instanceof Element && target.closest("[aria-haspopup]"))) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    held.push({ target, event: copy(event) });
  };

  const onKey = (event: KeyboardEvent) => {
    if (event.defaultPrevented || !isShortcut(shortcut, event)) return;
    event.preventDefault();
    if (!held.some((item) => item.event instanceof KeyboardEvent && item.event.key.toLowerCase() === event.key.toLowerCase())) held.push({ target: event.target ?? document, event: copy(event) });
    void start();
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
      document.removeEventListener("keydown", onKey, true);
    }
    for (const { target, event } of held.splice(0)) {
      if (target === document || (target instanceof Node && target.isConnected)) target.dispatchEvent(event);
    }
  }

  for (const name of STARTERS) element.addEventListener(name, start, { capture: true, passive: true });
  if (shortcut) document.addEventListener("keydown", onKey, true);
};

export default intent;
