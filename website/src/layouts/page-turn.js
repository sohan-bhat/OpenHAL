(() => {
  const key = "openhal:page-turn";
  let clicked;
  const section = (links, url) => {
    const base = new URL(links[0].href).pathname;
    const path = new URL(url, location.href).pathname;
    let found = path == base ? 0 : -1;
    let longest = 0;
    links.forEach((link, index) => {
      for (const prefix of link.dataset.match.split(" ")) {
        const full = base + prefix;
        if (prefix && path.startsWith(full) && full.length > longest) {
          found = index;
          longest = full.length;
        }
      }
    });
    return found;
  };
  addEventListener("click", (event) => (clicked = event.target.closest?.(".oh-sections a[data-match], .oh-menu-sections a, .oh-section-select a")?.href), true);
  addEventListener("pageswap", ({ viewTransition, activation }) => {
    if (!viewTransition) return;
    const links = [...document.querySelectorAll(".oh-sections a[data-match]")];
    const to = activation?.entry?.url;
    const from = links.length && to && clicked == to ? section(links, location.href) : -1;
    const next = from < 0 ? -1 : section(links, to);
    const turn = next >= 0 && next != from ? (next > from ? "forward" : "backward") : "";
    try {
      sessionStorage[key] = turn;
    } catch {}
    turn ? viewTransition.types.add(turn) : viewTransition.skipTransition();
  });
  addEventListener("pagereveal", ({ viewTransition }) => {
    if (!viewTransition) return;
    let turn;
    try {
      turn = sessionStorage[key];
      sessionStorage.removeItem(key);
    } catch {}
    if (turn == "forward" || turn == "backward") {
      viewTransition.types.add(turn);
      document.documentElement.dataset.turn = turn;
    } else viewTransition.skipTransition();
  });
})();
