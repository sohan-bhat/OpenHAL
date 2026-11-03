import { describe, expect, it } from "vitest";
import { KeyQueue, movesFocusLater } from "../../src/components/ui/keys-in-order";

interface Key {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

const press = (key: string, modifiers: Partial<Key> = {}): Key => ({ key, ctrlKey: false, metaKey: false, altKey: false, ...modifiers });

/** A list like Radix's, which moves focus in a timer, with a queue in front of it and timers run by hand. */
function list() {
  const timers: Array<() => void> = [];
  const later = (run: () => void) => timers.push(run);
  const items = ["Any", "Tier 1", "Tier 2"];
  let focused = 0;
  const chosen: string[] = [];
  const queue: KeyQueue<Key> = new KeyQueue<Key>((event) => keydown(event), undefined, later);
  const keydown = (event: Key) => {
    if (queue.hold(event)) return;
    if (event.key === "ArrowDown") {
      const next = Math.min(focused + 1, items.length - 1);
      later(() => (focused = next));
    }
    if (event.key === "Enter") chosen.push(items[focused]);
    queue.handled(event);
  };
  const runTimers = () => {
    while (timers.length > 0) timers.shift()!();
  };
  return { keydown, runTimers, chosen, focused: () => items[focused] };
}

describe("keys in order", () => {
  it("chooses the item an arrow key reached when Enter comes before the list's timer", () => {
    const menu = list();
    menu.keydown(press("ArrowDown"));
    menu.keydown(press("Enter"));
    expect(menu.chosen).toEqual([]);
    menu.runTimers();
    expect(menu.chosen).toEqual(["Tier 1"]);
  });

  it("replays held keys one at a time, each after the move before it", () => {
    const menu = list();
    menu.keydown(press("ArrowDown"));
    menu.keydown(press("ArrowDown"));
    menu.keydown(press("Enter"));
    menu.runTimers();
    expect(menu.focused()).toBe("Tier 2");
    expect(menu.chosen).toEqual(["Tier 2"]);
  });

  it("lets a key through at once when no move is pending", () => {
    const menu = list();
    menu.keydown(press("Enter"));
    expect(menu.chosen).toEqual(["Any"]);
  });

  it("knows which keys move focus later", () => {
    for (const key of ["ArrowDown", "ArrowUp", "Home", "End", "PageUp", "PageDown", "t"]) expect(movesFocusLater(press(key)), key).toBe(true);
    for (const key of ["Enter", "Escape", "Tab", " "]) expect(movesFocusLater(press(key)), key).toBe(false);
    expect(movesFocusLater(press("k", { metaKey: true }))).toBe(false);
  });

  it("never holds Escape or Tab, which the list doesn't act on through the focused item", () => {
    const queue = new KeyQueue<Key>(() => undefined, undefined, () => undefined);
    queue.handled(press("ArrowDown"));
    expect(queue.hold(press("Escape"))).toBe(false);
    expect(queue.hold(press("Tab"))).toBe(false);
    expect(queue.hold(press("Enter"))).toBe(true);
  });

  it("drops held keys when the list leaves the page before its move runs", () => {
    const replayed: string[] = [];
    const timers: Array<() => void> = [];
    const queue = new KeyQueue<Key>((event) => replayed.push(event.key), undefined, (run) => timers.push(run));
    queue.handled(press("ArrowDown"));
    queue.hold(press("Enter"));
    queue.cancel();
    while (timers.length > 0) timers.shift()!();
    expect(replayed).toEqual([]);
  });
});
