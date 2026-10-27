import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";
import { ASKED, IDS, nb, storyFacts, storyLines } from "../../src/lib/story/facts";
import { COUNTED, PLACED, step, type StepId } from "../../src/lib/story/script";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const scenario = scenarioFrom(readFileSync(scenarioFile, "utf8")) as any;
const facts = storyFacts(scenario);
const lines = storyLines(facts);
const byId = (id: string) => scenario.record.exchanges.find((exchange: any) => exchange.id === id);
const nozzle = byId(IDS.nozzle);
const flat = (text: string) => text.replace(/\s+/g, " ").trim();

async function storyTime(page: Page, t: number): Promise<void> {
  await page.evaluate((time) => {
    const story = document.querySelector<HTMLElement>("[data-story]")!;
    const stage = story.querySelector<HTMLElement>(".story-stage")!;
    const runway = story.querySelector<HTMLElement>(".story-runway")!;
    let y = 0;
    for (let el: HTMLElement | null = story; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    const top = parseFloat(getComputedStyle(stage).top) || 0;
    window.scrollTo({ top: y - top + (time * runway.offsetHeight) / parseFloat(runway.style.height), behavior: "instant" });
  }, t);
  await page.waitForTimeout(320);
}

const shown = (page: Page, selector: string) =>
  page.evaluate(
    (query) => [...document.querySelectorAll<HTMLElement>(query)].filter((el) => Number(getComputedStyle(el).opacity) > 0.9 && el.getClientRects().length > 0).map((el) => el.textContent!.replace(/\s+/g, " ").trim()),
    selector,
  );

const lit = (page: Page) => page.evaluate(() => [...document.querySelectorAll<HTMLElement>(".story-scene [data-lit][data-on]")].map((el) => el.dataset.cam!).sort());

const at = (selector: string) => `.story-scene ${selector}`;

const states: Record<Exclude<StepId, "intro">, Array<[string, string]>> = {
  ask: [[at("[data-cam=client] .person"), ASKED]],
  look: [
    [at("[data-cam=client] .said"), facts.look.method],
    [at("[data-cam=camera] .seen > *"), "corner lifting"],
  ],
  warm: [
    [at("[data-cam=printer] .figure > *"), nb(facts.bed.value)],
    [at("[data-cam=kernel] .verdict-line"), "granted"],
  ],
  hot: [
    [at("[data-cam=kernel] .verdict-line"), nozzle.error.data.name],
    [at("[data-cam=client] .said"), nozzle.error.data.name],
    [at("[data-cam=printer] .figure > *"), nb(facts.bed.value)],
  ],
  loose: [[at("[data-cam=camera] .seen > *"), "print loose"]],
  pause: [
    [at("[data-cam=printer] .word > *"), "paused"],
    [at("[data-cam=kernel] .verdict-line"), "granted"],
  ],
  cancel: [
    [at("[data-cam=kernel] .verdict-line"), "confirmation required"],
    [at("[data-cam=client] .said"), facts.cancel.status],
  ],
  wake: [
    [at("[data-cam=printer] .word > *"), "paused"],
    [at("[data-cam=camera] .seen > *"), "print loose"],
  ],
  end: [[at("[data-cam=kernel] .verdict-line"), "confirmation required"]],
};

test.describe("the landing story", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("pins the whole diagram, centered, at one size", async ({ page }) => {
    await page.goto("/");
    const story = page.locator("[data-story]");
    await expect(story).toHaveAttribute("data-camera", "");
    await expect(story).toHaveAttribute("data-ready", "");
    const sizes: string[] = [];
    for (const item of COUNTED) {
      await storyTime(page, item.from + item.length / 2);
      const box = await page.locator(".story-stage").boundingBox();
      const header = await page.locator(".site-header").evaluate((el) => el.getBoundingClientRect().height);
      expect(box!.y).toBeGreaterThanOrEqual(header - 1);
      expect(box!.y + box!.height).toBeLessThanOrEqual(900 + 1);
      expect(Math.abs(box!.y - header - (900 - box!.y - box!.height))).toBeLessThan(4);
      sizes.push(JSON.stringify(await page.locator(".story-scene [data-cam]").evaluateAll((items) => items.map((el) => [el.getBoundingClientRect().x, el.getBoundingClientRect().width]))));
      expect(await page.locator(".story-scene").evaluate((el) => getComputedStyle(el).transform)).toBe("none");
    }
    expect(new Set(sizes).size).toBe(1);
  });

  test("keeps every word inside its card", async ({ page }) => {
    for (const form of [{ width: 1440, height: 900 }, { width: 1200, height: 800 }, { width: 1100, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(form);
      await page.goto("/");
      await expect(page.locator("[data-story]")).toHaveAttribute("data-ready", "");
      for (const item of PLACED) {
        await storyTime(page, item.from + item.length / 2);
        const spills = await page.evaluate(() => {
          const out: string[] = [];
          for (const card of document.querySelectorAll<HTMLElement>(".story-scene .node, .story-scene .story-trace")) {
            const box = card.getBoundingClientRect();
            const style = getComputedStyle(card);
            const left = box.left + parseFloat(style.borderLeftWidth) + parseFloat(style.paddingLeft) - 1;
            const right = box.right - parseFloat(style.borderRightWidth) - parseFloat(style.paddingRight) + 1;
            const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
            for (let text = walker.nextNode(); text; text = walker.nextNode()) {
              const parent = text.parentElement!;
              if (!text.textContent!.trim() || parent.closest("[data-in]:not([data-on]), .visually-hidden") || !parent.getClientRects().length) continue;
              const range = document.createRange();
              range.selectNodeContents(text);
              for (const rect of range.getClientRects()) {
                if (rect.width > 1 && (rect.left < left || rect.right > right)) out.push(`${card.dataset.cam ?? "trace"}: ${text.textContent!.trim()}`);
              }
            }
          }
          return out;
        });
        expect(spills, `${form.width}x${form.height} ${item.id}`).toEqual([]);
      }
    }
  });

  test("changes each caption and the state it describes at the same moment", async ({ page }) => {
    await page.goto("/");
    for (const item of COUNTED) {
      const id = item.id as Exclude<StepId, "intro">;
      for (const t of [item.from + 1, item.from + item.length / 2, item.to - 1]) {
        await storyTime(page, t);
        expect(await shown(page, ".story-note"), `${id} at ${t}`).toEqual([flat(lines[id])]);
        expect(await shown(page, ".story-count > *")).toEqual([`${COUNTED.indexOf(item) + 1} / ${COUNTED.length}`]);
        expect(await lit(page)).toEqual([...item.lit].sort());
        for (const [selector, text] of states[id]) expect((await shown(page, selector)).join(" "), `${id} ${selector} at ${t}`).toContain(flat(text));
      }
    }
  });

  test("shows each step's messages under the diagram in the trace's words", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, step("hot").from + 20);
    const trace = (await shown(page, ".story-scene .story-trace ol")).join(" ");
    expect(trace).toContain(facts.nozzle.method);
    expect(trace).toContain(`error ${nozzle.error.code} ${nozzle.error.data.name}`);
    expect(trace).toContain(flat(facts.nozzle.refusal.reason));
    await storyTime(page, step("cancel").from + 20);
    expect((await shown(page, ".story-scene .story-trace ol")).join(" ")).toContain("pending");
  });

  test("changes no layout while it plays", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    await storyTime(page, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    const end = PLACED[PLACED.length - 1].to;
    for (let t = 0; t <= end; t += 7) await storyTime(page, t);
    expect(await layouts()).toBe(before);
  });

  test("lets a person skip it and lands on what follows with no large gap", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, step("warm").from + 10);
    await page.getByRole("link", { name: "Skip the demo" }).click();
    await expect(page).toHaveURL(/#safe$/);
    await expect(page.locator("#safe-title")).toBeInViewport();
    await storyTime(page, PLACED[PLACED.length - 1].to + 1);
    const gap = await page.evaluate(() => document.querySelector("#safe-title")!.getBoundingClientRect().top - document.querySelector(".story-stage")!.getBoundingClientRect().bottom);
    expect(gap).toBeLessThan(120);
  });

  test("keeps every word on the stage at 13 px or more", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await storyTime(page, PLACED[PLACED.length - 1].from + 10);
      const smallest = await page.evaluate(() => {
        const walker = document.createTreeWalker(document.querySelector(".story-stage")!, NodeFilter.SHOW_TEXT);
        let least = Infinity;
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (node.textContent!.trim() && node.parentElement) least = Math.min(least, parseFloat(getComputedStyle(node.parentElement).fontSize));
        }
        return least;
      });
      expect(smallest).toBeGreaterThanOrEqual(13);
    }
  });

  test("with reduced motion it is a list of the same steps", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-camera", "");
    await expect(page.locator(".story-scene")).toBeHidden();
    const steps = page.locator(".story-list > li");
    await expect(steps).toHaveCount(COUNTED.length);
    for (const item of COUNTED) await expect(page.locator(".story-list")).toContainText(lines[item.id as Exclude<StepId, "intro">]);
    await expect(page.locator(".story-list")).toContainText(nozzle.error.data.name);
    await expect(page.locator(".story-list .story-snap").first()).toBeVisible();
  });

  test("fits a phone's screen and never scrolls sideways", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator("[data-story]")).toHaveAttribute("data-camera", "");
    for (const item of PLACED) {
      await storyTime(page, item.from + item.length / 2);
      const box = await page.locator(".story-stage").boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(844 + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      for (const node of await page.locator(".story-scene [data-cam]").all()) {
        const area = await node.boundingBox();
        expect(area!.x).toBeGreaterThanOrEqual(0);
        expect(area!.x + area!.width).toBeLessThanOrEqual(390);
      }
    }
  });
});

test.describe("smooth scrolling", () => {
  test("is a switch that is on by default, turns off and remembers it", async ({ page }) => {
    await page.goto("/");
    const toggle = page.getByRole("switch", { name: "Smooth scrolling" });
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await toggle.focus();
    await page.keyboard.press("Space");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await page.reload();
    await expect(page.getByRole("switch", { name: "Smooth scrolling" })).toHaveAttribute("aria-checked", "false");
    await page.getByRole("switch", { name: "Smooth scrolling" }).click();
    await page.reload();
    await expect(page.getByRole("switch", { name: "Smooth scrolling" })).toHaveAttribute("aria-checked", "true");
  });

  test("is off under reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const toggle = page.getByRole("switch", { name: "Smooth scrolling" });
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await expect(toggle).toBeDisabled();
  });

  test("eases the wheel and leaves keyboard and anchor scrolling alone", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "wheel timing is checked in one engine");
    await page.goto("/");
    await page.waitForTimeout(2500);
    await page.mouse.move(700, 450);
    const start = await page.evaluate(() => window.scrollY);
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(40);
    const early = await page.evaluate(() => window.scrollY);
    await page.waitForTimeout(900);
    const settled = await page.evaluate(() => window.scrollY);
    expect(early).toBeLessThan(settled);
    expect(Math.abs(settled - start - 400)).toBeLessThan(6);
    await page.keyboard.press("End");
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => Math.abs(window.scrollY + innerHeight - document.documentElement.scrollHeight))).toBeLessThan(2);
  });
});
