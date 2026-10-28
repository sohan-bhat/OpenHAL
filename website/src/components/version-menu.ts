/** Keeps the header's version button's aria-expanded in step with its menu, and closes the menu when focus leaves it. */
export function versionMenu(): void {
  const menu = document.getElementById("version-menu");
  const button = document.querySelector<HTMLButtonElement>(".version-button");
  if (!menu || !button) return;
  menu.addEventListener("toggle", (event) => {
    button.ariaExpanded = String((event as ToggleEvent).newState === "open");
  });
  menu.addEventListener("focusout", (event) => {
    const next = event.relatedTarget as Node | null;
    if (next && next !== button && !menu.contains(next) && menu.matches(":popover-open")) menu.hidePopover();
  });
}
