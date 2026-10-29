import { CLOSE, OPEN, release, still, tween } from "./motion";

type Theme = "auto" | "light" | "dark";

declare global {
  interface Window {
    StarlightThemeProvider?: { updatePickers(theme?: string): void };
  }
}

const anchored = CSS.supports("anchor-scope: all") && CSS.supports("position-area: block-end");
const themeKey = "starlight-theme";
const light = matchMedia("(prefers-color-scheme: light)");
const ready = new WeakSet<Element>();
let floating: Promise<typeof import("@floating-ui/dom")> | undefined;

const parseTheme = (value: unknown): Theme => (value === "light" || value === "dark" ? value : "auto");

/** Applies a theme the way Starlight's own picker does, and keeps the choice in this browser. */
function setTheme(theme: Theme): void {
  window.StarlightThemeProvider?.updatePickers(theme);
  document.documentElement.dataset.theme = theme === "auto" ? (light.matches ? "light" : "dark") : theme;
  try {
    localStorage.setItem(themeKey, theme === "auto" ? "" : theme);
  } catch {}
}

const lift = (above: boolean, part = 1) => `translateY(${(above ? 4 : -4) * part}px) scale(0.98)`;

/**
 * A menu button on a native popover list. The browser opens and closes the list, including on a
 * click outside, and this adds the arrow keys, Escape, focus, the theme choice and the motion.
 */
function setup(picker: HTMLElement): void {
  const button = picker.querySelector<HTMLButtonElement>(".oh-picker-button");
  const list = picker.querySelector<HTMLElement>(".oh-picker-list");
  if (!button || !list) return;
  const caret = button.querySelector("svg");
  const start = picker.dataset.align === "start";
  const items = () => [...list.querySelectorAll<HTMLElement>("[role^='menuitem']")];
  const chosen = () => items().find((item) => item.matches("[aria-current], [aria-checked='true']"));
  const above = () => list.getBoundingClientRect().top < button.getBoundingClientRect().top;
  const focus = (item: HTMLElement | undefined) => item?.focus({ preventScroll: true });
  let turn = 0;
  let last = false;
  let stop: (() => void) | undefined;

  list.tabIndex = -1;
  for (const item of items()) item.tabIndex = -1;
  button.setAttribute("aria-expanded", String(list.matches(":popover-open")));

  function move(by: number | "first" | "last"): void {
    const all = items();
    const at = all.indexOf(document.activeElement as HTMLElement);
    if (by === "first") return focus(all[0]);
    if (by === "last") return focus(all[all.length - 1]);
    focus(all[at < 0 ? (by > 0 ? 0 : all.length - 1) : (at + by + all.length) % all.length]);
  }

  async function place(): Promise<void> {
    if (anchored || !button || !list) return;
    try {
      const { autoUpdate, computePosition, flip, offset, shift } = await (floating ??= import("@floating-ui/dom"));
      const update = () =>
        computePosition(button, list, { strategy: "fixed", placement: start ? "bottom-start" : "bottom-end", middleware: [offset(4), flip(), shift({ padding: 8 })] }).then(({ x, y }) => {
          Object.assign(list.style, { left: `${x}px`, top: `${y}px`, minWidth: `${Math.max(button.offsetWidth, 112)}px` });
        });
      stop?.();
      stop = autoUpdate(button, list, update);
      await update();
    } catch {
      floating = undefined;
    }
  }

  async function show(mine: number, settled: boolean): Promise<void> {
    await place();
    if (mine !== turn) return;
    if (still()) return release(list, "opacity");
    const up = above();
    list.style.transformOrigin = `${start ? "left" : "right"} ${up ? "bottom" : "top"}`;
    await tween(list, { opacity: [settled ? 0 : null, 1], transform: [settled ? lift(up) : null, "none"] }, OPEN);
    if (mine === turn) release(list, "opacity", "transform", "transform-origin");
  }

  async function hide(mine: number): Promise<void> {
    if (!still()) {
      const up = above();
      list.setAttribute("data-closing", "");
      list.style.transformOrigin = `${start ? "left" : "right"} ${up ? "bottom" : "top"}`;
      await tween(list, { opacity: [null, 0], transform: [null, lift(up, 0.5)] }, CLOSE);
      if (mine !== turn) return;
      list.removeAttribute("data-closing");
      release(list, "opacity", "transform", "transform-origin");
    }
    stop?.();
    stop = undefined;
  }

  list.addEventListener("beforetoggle", (event) => {
    const opening = (event as ToggleEvent).newState === "open";
    const mine = ++turn;
    button.setAttribute("aria-expanded", String(opening));
    if (caret) {
      if (still()) caret.style.rotate = opening ? "180deg" : "";
      else void tween(caret, { rotate: [null, opening ? "180deg" : "0deg"] }, opening ? OPEN : CLOSE);
    }
    if (!opening) return void hide(mine);
    const settled = !list.hasAttribute("data-closing");
    list.removeAttribute("data-closing");
    if (settled && (!anchored || !still())) list.style.opacity = "0";
    requestAnimationFrame(() => void show(mine, settled));
  });

  list.addEventListener("toggle", (event) => {
    if ((event as ToggleEvent).newState !== "open") return;
    if (last) move("last");
    else focus(chosen() ?? items()[0]);
    last = false;
  });

  button.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    if (list.matches(":popover-open")) return move(event.key === "ArrowDown" ? "first" : "last");
    last = event.key === "ArrowUp" && !chosen();
    button.click();
  });

  list.addEventListener("keydown", (event) => {
    const active = document.activeElement;
    const key = event.key;
    if (key === "ArrowDown") move(1);
    else if (key === "ArrowUp") move(-1);
    else if (key === "Home") move("first");
    else if (key === "End") move("last");
    else if (key === "Escape") {
      list.hidePopover();
      button.focus();
    } else if (key === " " && active instanceof HTMLAnchorElement) active.click();
    else if (key.length === 1 && key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const all = items();
      const from = all.indexOf(active as HTMLElement) + 1;
      focus([...all.slice(from), ...all.slice(0, from)].find((item) => item.textContent?.trim().toLowerCase().startsWith(key.toLowerCase())));
    } else return;
    event.preventDefault();
  });

  list.addEventListener("click", (event) => {
    const item = (event.target as Element).closest<HTMLElement>("[role^='menuitem']");
    if (!item) return;
    const theme = item.dataset.value;
    if (theme) setTheme(parseTheme(theme));
    list.hidePopover();
    if (theme) button.focus();
  });

  picker.addEventListener("focusout", (event) => {
    const next = event.relatedTarget as Node | null;
    if (next && !picker.contains(next) && list.matches(":popover-open")) list.hidePopover();
  });
}

customElements.define(
  "oh-picker",
  class extends HTMLElement {
    connectedCallback(): void {
      if (ready.has(this)) return;
      ready.add(this);
      setup(this);
    }
  },
);
