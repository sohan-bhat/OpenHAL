import { describe, expect, it } from "vitest";
import { PRODUCT_NAME } from "../../src/config/brand";
import { AWAY, DIM, FALLS, LEAVES, LOW, PARTS, SLIDE, STEP, TOTAL, briefSpan, fading, stepSpan, strength } from "../../src/lib/story/wordmark";

const letters = [...PRODUCT_NAME];
const current = (t: number) => letters.map((_, at) => strength(fading(PRODUCT_NAME, at), t));

describe("the wordmark sequence", () => {
  it("spells H, A and L in the order the word has them, under the hero's labels", () => {
    expect(PARTS.map((part) => part.letter)).toEqual(["H", "A", "L"]);
    expect(PARTS.map((part) => part.label)).toEqual(["[hardware]", "[agent]", "[layer]"]);
    const places = PARTS.map((part) => PRODUCT_NAME.lastIndexOf(part.letter));
    expect([...places].sort((a, b) => a - b)).toEqual(places);
    expect(TOTAL).toBe(AWAY + 3 * STEP);
  });

  it("lets the description leave before the word comes down, and the word land before H lights", () => {
    expect(FALLS).toBeLessThan(LEAVES);
    expect(LEAVES).toBeLessThan(AWAY);
    expect(stepSpan(0)[0]).toBe(AWAY);
  });

  it("keeps every letter at full strength at rest and lights one letter in each step", () => {
    expect(current(0)).toEqual(letters.map(() => 1));
    for (const [index, part] of PARTS.entries()) {
      const [from] = stepSpan(index);
      const settled = from + (index === 0 ? DIM : SLIDE) + 1;
      const shown = current(settled);
      for (const [at, letter] of letters.entries()) {
        expect(shown[at], `${part.letter} step, letter ${letter}`).toBeCloseTo(at === PRODUCT_NAME.lastIndexOf(part.letter) ? 1 : LOW, 5);
      }
    }
  });

  it("hands strength from one letter to the next while the word slides, and plays backwards the same way", () => {
    for (let t = 0; t <= TOTAL; t += 0.25) {
      const shown = current(t);
      for (const value of shown) {
        expect(value).toBeGreaterThanOrEqual(LOW - 1e-9);
        expect(value).toBeLessThanOrEqual(1 + 1e-9);
      }
      expect(current(t)).toEqual(shown);
    }
    const middle = stepSpan(1)[0] + SLIDE / 2;
    const shown = current(middle);
    expect(shown[PRODUCT_NAME.lastIndexOf("H")]).toBeCloseTo((1 + LOW) / 2, 5);
    expect(shown[PRODUCT_NAME.lastIndexOf("A")]).toBeCloseTo((1 + LOW) / 2, 5);
  });

  it("shows each brief once its letter is current and the word has stopped, one at a time", () => {
    for (const [index] of PARTS.entries()) {
      const [start, end] = briefSpan(index);
      const [from, to] = stepSpan(index);
      expect(start).toBeGreaterThan(from);
      expect(end).toBe(to);
      if (index > 0) expect(start).toBeGreaterThanOrEqual(briefSpan(index - 1)[1]);
    }
  });

  it("writes each brief in plain sentences that follow the owner's rules", () => {
    for (const part of PARTS) {
      expect(part.brief).toMatch(/^[A-Z].*[.]$/);
      expect(part.brief).not.toMatch(/[;:!–—]/);
      expect(part.brief).not.toMatch(/\bAI\b/);
      expect(part.brief).not.toMatch(/\b(it|its|them|they)\b/i);
      expect(part.brief.split(/(?<=[.])\s+/).length).toBeLessThanOrEqual(2);
    }
  });
});
