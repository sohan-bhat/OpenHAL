(() => {
  const box = document.currentScript.previousElementSibling;
  const tabs = [...box.querySelectorAll("[role=tab]")];
  const system = navigator.userAgentData?.platform || navigator.platform || navigator.userAgent;
  const pick = (/^Win|Windows/.test(system) && tabs.find((tab) => tab.dataset.platform === "windows")) || tabs[0];
  if (!pick) return;
  box.dataset.default = pick.dataset.channel;
  for (const tab of tabs) {
    const on = tab === pick;
    tab.setAttribute("aria-selected", String(on));
    tab.dataset.state = on ? "active" : "inactive";
    tab.tabIndex = on ? 0 : -1;
  }
  for (const panel of box.querySelectorAll("[role=tabpanel]")) panel.dataset.state = panel.dataset.channel === pick.dataset.channel ? "active" : "inactive";
})();
