import { describe, expect, it } from "vitest";
import { PITCH, PRODUCT_LONG_NAME, PRODUCT_NAME } from "../../src/config/brand";
import { LEDE, SPELLED } from "../../src/lib/story/name";

describe("the hero", () => {
  it("spells H, A and L out as the owner wrote the labels, in the order the word has them", () => {
    expect(SPELLED.map((part) => part.letter)).toEqual(["H", "A", "L"]);
    expect(SPELLED.map((part) => part.label)).toEqual(["[hardware]", "[abstraction]", "[layer]"]);
    const places = SPELLED.map((part) => PRODUCT_NAME.lastIndexOf(part.letter));
    expect([...places].sort((a, b) => a - b)).toEqual(places);
    expect(PRODUCT_LONG_NAME.split(" ").slice(1).map((word) => `[${word.toLowerCase()}]`)).toEqual(SPELLED.map((part) => part.label));
  });

  it("says what OpenHAL does in the owner's two sentences", () => {
    expect(PITCH).toBe("An open-source protocol for AI agents to control hardware.");
    expect(LEDE).toBe("Agents send requests to the OpenHAL hub, which checks each one against limits you set before anything reaches the device.");
    for (const sentence of [PITCH, LEDE]) expect(sentence).not.toMatch(/[;:!–—]/);
  });
});
