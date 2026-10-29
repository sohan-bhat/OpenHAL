const intents = ["pointerover", "pointerdown", "focusin", "keydown", "touchstart"];

/**
 * Loads the pickers' keys, the theme choice and the motion on a person's first interaction, never
 * while the page loads. Until then the pickers open as native popovers.
 */
function load(): void {
  for (const kind of intents) removeEventListener(kind, load, { capture: true });
  import("./live").catch(() => listen());
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) import("motion/mini").catch(() => {});
}

function listen(): void {
  for (const kind of intents) addEventListener(kind, load, { capture: true, passive: true });
}

listen();

matchMedia("(prefers-color-scheme: light)").addEventListener("change", ({ matches }) => {
  try {
    if (localStorage.getItem("starlight-theme")) return;
  } catch {}
  document.documentElement.dataset.theme = matches ? "light" : "dark";
});
