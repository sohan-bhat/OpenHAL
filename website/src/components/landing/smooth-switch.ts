const KEY = "openhal:smooth-scroll";

function stored(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function save(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    return;
  }
}

function idle(run: () => void): void {
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 2000 });
  else window.setTimeout(run, 200);
}

/**
 * Wires the Smooth scrolling switch. Smooth scrolling is on unless the person turned it off, which
 * this browser remembers, and always off under prefers-reduced-motion. The easing itself loads
 * once the page is idle, and only while the switch is on.
 */
export function smoothSwitch(toggle: HTMLButtonElement): void {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  let stop: (() => void) | null = null;
  let loading = false;

  const apply = () => {
    const on = !reduce.matches && stored() !== "off";
    toggle.setAttribute("aria-checked", String(on));
    toggle.disabled = reduce.matches;
    if (on && !stop && !loading) {
      loading = true;
      idle(() => {
        import("./smooth-scroll").then(({ smooth }) => {
          loading = false;
          if (toggle.getAttribute("aria-checked") === "true" && !stop) stop = smooth();
        });
      });
    }
    if (!on && stop) {
      stop();
      stop = null;
    }
  };

  toggle.addEventListener("click", () => {
    save(toggle.getAttribute("aria-checked") !== "true");
    apply();
  });
  reduce.addEventListener("change", apply);
  toggle.hidden = false;
  apply();
}
