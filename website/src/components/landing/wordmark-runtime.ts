/**
 * Measures where the wordmark comes down to and how far it slides, from the letters themselves, so
 * the current letter lands where H stood at any size and the briefs sit under the word. The word
 * and the tallest brief are centred in the stage together, and the result is written as custom
 * properties the stylesheet reads with the story time.
 */
export function wordmark(root: HTMLElement): (pin: number) => void {
  const stage = root.querySelector<HTMLElement>(".hero-stage");
  const name = root.querySelector<HTMLElement>(".hero-name");
  const letters = root.querySelector<HTMLElement>(".hero-letters");
  const briefs = Array.from(root.querySelectorAll<HTMLElement>(".hero-brief"));
  const left = (letter: string) => letters?.querySelector<HTMLElement>(`[data-letter="${letter}"]`)?.offsetLeft ?? 0;
  const set = (name: string, value: number) => root.style.setProperty(name, `${Math.round(value)}px`);
  return () => {
    if (!stage || !name || !letters) return;
    const anchor = left("H");
    set("--slide-a", left("A") - anchor);
    set("--slide-l", left("L") - anchor);
    set("--anchor", name.offsetLeft + letters.offsetLeft + anchor);
    const word = letters.offsetHeight;
    const gap = word * 0.22 + 12;
    const tallest = Math.max(0, ...briefs.map((brief) => brief.offsetHeight));
    const top = Math.max(name.offsetTop, (stage.clientHeight - word - gap - tallest) / 2);
    set("--down", top - name.offsetTop);
    set("--brief-top", top + word + gap);
  };
}
