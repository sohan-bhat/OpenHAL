import * as React from "react";

type KeyLike = Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey">;

const MOVES = new Set(["ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]);

/**
 * Keys a list never acts on through the focused item. Radix closes on Escape from a document
 * listener before the list sees the key, and a replayed Tab would be synthetic, which a browser
 * never lets move focus, so both go through at once.
 */
const PASSED = new Set(["Escape", "Tab"]);

/** True for a key after which a Radix list moves focus in a timer: an arrow, Home, End, a page key or a typed letter. */
export function movesFocusLater(event: KeyLike): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return MOVES.has(event.key) || (event.key.length === 1 && event.key !== " ");
}

/**
 * Runs a list's keys in the order they were pressed.
 *
 * Radix Select and DropdownMenu move focus for an arrow key, Home, End or a typed letter in a
 * timer. A busy browser runs the next key press before that timer, so Enter right after ArrowDown
 * chose the item the list was leaving. A key that arrives while a move is pending is held and
 * replayed, one at a time, once the move has run. Escape and Tab are never held.
 */
export class KeyQueue<E extends KeyLike> {
  private pending = false;
  private readonly held: E[] = [];

  constructor(
    private readonly replay: (event: E) => void,
    private readonly copy: (event: E) => E = (event) => event,
    private readonly later: (run: () => void) => void = (run) => window.setTimeout(run),
  ) {}

  /** Holds a copy of the key when a move is pending. True means the list must ignore the original. */
  hold(event: E): boolean {
    if (!this.pending || PASSED.has(event.key)) return false;
    this.held.push(this.copy(event));
    return true;
  }

  /**
   * Marks a move as pending after the list handled a key that moves focus later. The release waits
   * two timers, so it runs after the list's own timer whether the list set that timer before or
   * after this call.
   */
  handled(event: E): void {
    if (!movesFocusLater(event)) return;
    this.pending = true;
    this.later(() => this.later(() => this.release()));
  }

  /** Drops the held keys, for a list that left the page before its move ran. */
  cancel(): void {
    this.pending = false;
    this.held.length = 0;
  }

  private release(): void {
    this.pending = false;
    while (!this.pending && this.held.length > 0) this.replay(this.held.shift()!);
  }
}

function copyKey(event: KeyboardEvent): KeyboardEvent {
  const { key, code, location, shiftKey, ctrlKey, altKey, metaKey } = event;
  return new KeyboardEvent("keydown", { key, code, location, shiftKey, ctrlKey, altKey, metaKey, bubbles: true, cancelable: true, composed: true });
}

/** The two handlers a Radix list's content needs so its keys keep their order. */
export function useKeysInOrder(): { onKeyDownCapture: React.KeyboardEventHandler; onKeyDown: React.KeyboardEventHandler } {
  const queue = React.useMemo(() => new KeyQueue<KeyboardEvent>((event) => (document.activeElement ?? document.body).dispatchEvent(event), copyKey), []);
  React.useEffect(() => () => queue.cancel(), [queue]);
  return React.useMemo(
    () => ({
      onKeyDownCapture: (event: React.KeyboardEvent) => {
        if (!queue.hold(event.nativeEvent)) return;
        event.preventDefault();
        event.stopPropagation();
      },
      onKeyDown: (event: React.KeyboardEvent) => queue.handled(event.nativeEvent),
    }),
    [queue],
  );
}
