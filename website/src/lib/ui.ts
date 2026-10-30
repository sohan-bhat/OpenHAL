import { CLOSE, OPEN, release, still, tween, warm } from "./motion";

const keepsContent = CSS.supports("selector(::details-content)");

/** Fades the phone menu in and out, which stays drawn while it fades out. */
function phoneMenu(): void {
  const pane = document.getElementById("starlight__sidebar");
  const content = pane?.querySelector<HTMLElement>(".sidebar-content");
  if (!pane || !content) return;
  let turn = 0;
  const settle = (mine: number) => {
    if (mine !== turn) return;
    pane.removeAttribute("data-closing");
    release(pane, "opacity");
    release(content, "transform");
  };
  pane.addEventListener("beforetoggle", (event) => {
    if (still()) return;
    const mine = ++turn;
    if ((event as ToggleEvent).newState === "open") {
      const settled = !pane.hasAttribute("data-closing");
      pane.removeAttribute("data-closing");
      if (settled) pane.style.opacity = "0";
      void tween(content, { transform: [settled ? "translateY(-8px)" : null, "none"] }, OPEN);
      void tween(pane, { opacity: [settled ? 0 : null, 1] }, OPEN).then(() => settle(mine));
    } else {
      pane.setAttribute("data-closing", "");
      void tween(content, { transform: [null, "translateY(-4px)"] }, CLOSE);
      void tween(pane, { opacity: [null, 0] }, CLOSE).then(() => settle(mine));
    }
  });
}

const turns = new WeakMap<Element, number>();

function next(element: Element): number {
  const turn = (turns.get(element) ?? 0) + 1;
  turns.set(element, turn);
  return turn;
}

/**
 * Opens and closes a disclosure, whatever toggles it. A sidebar group or the Playground's builder
 * grows and shrinks, and the phone's outline drops in and out. A closing disclosure keeps its
 * content drawn until the motion ends.
 */
function disclosure(details: HTMLDetailsElement): void {
  const body = details.lastElementChild;
  if (still() || !(body instanceof HTMLElement) || body.localName === "summary") return;
  const opening = details.open;
  if (!opening && !keepsContent) return;
  const mine = next(details);
  const settled = !details.hasAttribute("data-closing");
  details.toggleAttribute("data-closing", !opening);
  const done = () => {
    if (turns.get(details) !== mine) return;
    details.removeAttribute("data-closing");
    release(body, "height", "opacity", "transform", "overflow");
  };
  if (details.closest("mobile-starlight-toc")) {
    if (opening && settled) body.style.opacity = "0";
    const frames = opening ? { opacity: [settled ? 0 : null, 1], transform: [settled ? "translateY(-4px)" : null, "none"] } : { opacity: [null, 0], transform: [null, "translateY(-4px)"] };
    void tween(body, frames, opening ? OPEN : CLOSE).then(done);
    return;
  }
  const height = opening ? `${body.scrollHeight}px` : "0px";
  body.style.overflow = "hidden";
  if (opening && settled) Object.assign(body.style, { height: "0px", opacity: "0" });
  const frames = opening ? { height: [settled ? "0px" : null, height], opacity: [settled ? 0 : null, 1] } : { height: [null, height], opacity: [null, 0] };
  void tween(body, frames, opening ? OPEN : CLOSE).then(done);
}

/** Lets a Copy button's old word leave as the new one arrives, once the button shows Copied or Copy. */
function swap(button: HTMLElement): void {
  const [copy, copied] = [...button.children] as HTMLElement[];
  if (still() || !copy || !copied) return;
  const mine = next(button);
  const [leaving, arriving] = button.hasAttribute("data-copied") ? [copy, copied] : [copied, copy];
  for (const label of [leaving, arriving]) label.style.visibility = "visible";
  arriving.style.opacity = "0";
  void tween(leaving, { opacity: [null, 0], transform: [null, "translateY(-6px)"] }, OPEN);
  void tween(arriving, { opacity: [0, 1], transform: ["translateY(6px)", "none"] }, OPEN).then(() => {
    if (turns.get(button) !== mine) return;
    for (const label of [leaving, arriving]) release(label, "visibility", "opacity", "transform");
  });
}

function observe(): void {
  new MutationObserver((records) => {
    const was = new Map<Element, string | null>();
    for (const { target, oldValue } of records) if (target instanceof Element && !was.has(target)) was.set(target, oldValue);
    for (const [target, oldValue] of was) {
      if (target instanceof HTMLDetailsElement && (oldValue !== null) !== target.open) disclosure(target);
      else if (target instanceof HTMLButtonElement && target.classList.contains("copy-button") && (oldValue !== null) !== target.hasAttribute("data-copied")) swap(target);
    }
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ["open", "data-copied"], attributeOldValue: true });
}

phoneMenu();
observe();
if (!still()) warm().catch(() => {});
