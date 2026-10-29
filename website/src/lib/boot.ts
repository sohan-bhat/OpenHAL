const intents = ["pointerover", "pointerdown", "focusin", "keydown", "touchstart"];

/**
 * Loads Motion and the motion for Starlight's parts on a person's first interaction, never while
 * the page loads.
 */
function load(): void {
  for (const kind of intents) removeEventListener(kind, load, { capture: true });
  import("./ui").catch(() => listen());
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
