if (/mac|iphone|ipad/i.test(navigator.userAgentData?.platform || navigator.platform || "")) document.documentElement.classList.add("apple");
(() => {
  const key = "openhal:page-turn";
  let clicked = null;
  const section = (links, url) => {
    const base = new URL(links[0].href).pathname;
    const path = new URL(url, location.href).pathname;
    if (path === base) return 0;
    let found = -1;
    let longest = 0;
    links.forEach((link, index) => {
      for (const prefix of (link.dataset.match || "").split(" ")) {
        const full = base + prefix;
        if (prefix && path.startsWith(full) && full.length > longest) {
          found = index;
          longest = full.length;
        }
      }
    });
    return found;
  };
  addEventListener(
    "click",
    (event) => {
      const link = event.target instanceof Element ? event.target.closest(".desktop-nav a[data-match], .mobile-nav a") : null;
      clicked = link ? link.href : null;
    },
    true,
  );
  addEventListener("pageswap", (event) => {
    if (!event.viewTransition) return;
    const links = Array.from(document.querySelectorAll(".desktop-nav a[data-match]"));
    const to = event.activation && event.activation.entry ? event.activation.entry.url : null;
    let turn = null;
    if (links.length && to && clicked === to) {
      const from = section(links, location.href);
      const next = section(links, to);
      if (from >= 0 && next >= 0 && from !== next) turn = next > from ? "forward" : "backward";
    }
    try {
      if (turn) sessionStorage.setItem(key, turn);
      else sessionStorage.removeItem(key);
    } catch {}
    if (turn) event.viewTransition.types.add(turn);
    else event.viewTransition.skipTransition();
  });
  addEventListener("pagereveal", (event) => {
    if (!event.viewTransition) return;
    let turn = null;
    try {
      turn = sessionStorage.getItem(key);
      sessionStorage.removeItem(key);
    } catch {}
    if (turn === "forward" || turn === "backward") {
      event.viewTransition.types.add(turn);
      document.documentElement.dataset.turn = turn;
    } else event.viewTransition.skipTransition();
  });
})();
