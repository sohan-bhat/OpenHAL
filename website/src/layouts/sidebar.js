const data = document.documentElement.dataset;
const key = "openhal:sidebar";
const button = document.querySelector(".side-toggle");
const aside = button.parentElement;
const nav = aside.querySelector("nav");
let timer;
let settle;
const hidden = () => data.sidebar == "hidden";
const name = () => {
  button.ariaExpanded = !hidden();
  button.ariaLabel = (hidden() ? "Show" : "Hide") + " the sidebar";
};
const move = (change) => {
  clearTimeout(settle);
  data.moving = "";
  change();
  settle = setTimeout(() => {
    delete data.moving;
    hidden() || delete data.peek;
  }, 250);
};
const peek = (on) => {
  clearTimeout(timer);
  hidden() && on != "peek" in data && move(() => (on ? (data.peek = "") : delete data.peek));
};
const sync = () => {
  let hide;
  try {
    hide = localStorage[key] == "hidden";
  } catch {}
  delete data.moving;
  delete data.peek;
  data.sidebar = hide ? "hidden" : "shown";
  name();
};
button.onclick = () => {
  move(() => (data.sidebar = hidden() ? "shown" : "hidden") == "hidden" && delete data.peek);
  try {
    localStorage[key] = data.sidebar;
  } catch {}
  name();
};
button.onkeydown = (event) => {
  const first = nav.querySelector("a,summary");
  if (event.key == "Tab" && !event.shiftKey && hidden() && !("peek" in data) && first) {
    event.preventDefault();
    peek(1);
    first.focus({ preventScroll: true });
  }
};
aside.onpointerover = (event) => {
  clearTimeout(timer);
  if (event.target.matches(".side-edge") && event.pointerType == "mouse" && !event.buttons) timer = setTimeout(peek, 80, 1);
};
aside.onpointerleave = () => {
  clearTimeout(timer);
  nav.querySelector(":focus-visible") || (timer = setTimeout(peek, 300, 0));
};
addEventListener("focusin", (event) => aside.contains(event.target) || peek(0));
addEventListener("keydown", (event) => {
  if (event.key == "Escape" && "peek" in data && hidden()) {
    aside.contains(document.activeElement) && button.focus();
    peek(0);
  }
});
onpageshow = (event) => event.persisted && sync();
document.onprerenderingchange = sync;
name();
