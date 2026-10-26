import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";
import { SNAP_AT } from "../../src/lib/story/timeline";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const exchanges = scenarioFrom(readFileSync(scenarioFile, "utf8")).record.exchanges as any[];
const writes = exchanges.filter((exchange) => exchange.request.method === "hal/write");
const bed = writes.find((exchange) => exchange.result);
const nozzle = writes.find((exchange) => exchange.error);
const cancel = exchanges.find((exchange) => exchange.result?.status === "pending");
const degrees = (exchange: any) => `${exchange.request.params.value} °C`;
const nb = (text: string) => text.replace(/(\d) /g, "$1 ");
const people = (text: string) => text.replace(/(\d) degC\b/g, "$1 °C");

async function storyTime(page: Page, t: number): Promise<void> {
  await page.evaluate((time) => {
    const story = document.querySelector<HTMLElement>("[data-story]")!;
    const stage = story.querySelector<HTMLElement>(".story-stage")!;
    let y = 0;
    for (let el: HTMLElement | null = story; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
    const pin = document.querySelector<HTMLElement>(".site-header")!.offsetHeight;
    const total = parseFloat(getComputedStyle(story).getPropertyValue("--runway"));
    window.scrollTo(0, y - pin + (time * (story.offsetHeight - stage.offsetHeight)) / total);
  }, t);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

const shown = (page: Page, selector: string) =>
  page.evaluate((query) => [...document.querySelectorAll<HTMLElement>(query)].filter((el) => Number(getComputedStyle(el).opacity) > 0.9).map((el) => el.textContent!.trim()), selector);

const total = (page: Page) => page.locator("[data-story]").evaluate((story) => parseFloat(getComputedStyle(story).getPropertyValue("--runway")));

test.describe("the landing story", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("pins its stage under the header and moves its camera with the scroll", async ({ page }) => {
    await page.goto("/");
    const story = page.locator("[data-story]");
    await expect(story).toHaveAttribute("data-camera", "");
    await expect(story).toHaveAttribute("data-ready", "");
    await storyTime(page, 0);
    const wide = await page.locator(".story-scene").evaluate((scene) => scene.style.transform);
    await storyTime(page, SNAP_AT.look);
    const close = await page.locator(".story-scene").evaluate((scene) => scene.style.transform);
    expect(close).toMatch(/^translate\(.+\) scale\(.+\)$/);
    expect(close).not.toBe(wide);
    const top = await page.locator(".story-stage").evaluate((stage) => stage.getBoundingClientRect().top);
    expect(top).toBe(await page.locator(".site-header").evaluate((header) => (header as HTMLElement).offsetHeight));
  });

  test("plays the record's answers on the stage", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, SNAP_AT.look);
    expect(await shown(page, ".story-scene [data-cam=camera] .seen > *")).toEqual(["corner lifting"]);
    await storyTime(page, SNAP_AT.warm);
    expect(await shown(page, ".story-scene [data-cam=kernel] .verdict-box")).toEqual(["granted"]);
    await storyTime(page, SNAP_AT.heat);
    expect(await shown(page, ".story-scene [data-cam=printer] .figure > *")).toEqual([nb(degrees(bed))]);
    await storyTime(page, SNAP_AT.hot);
    expect(await shown(page, ".story-scene [data-cam=kernel] .verdict-box")).toEqual([nozzle.error.data.name]);
    await storyTime(page, SNAP_AT.reply);
    const reply = (await shown(page, ".story-scene [data-cam=client] .said")).join(" ");
    expect(reply).toContain(nb(people(nozzle.error.message.split(" (")[0])));
    expect(reply).toContain(nb(degrees(nozzle)));
    await storyTime(page, SNAP_AT.loose);
    expect(await shown(page, ".story-scene [data-cam=camera] .seen > *")).toEqual(["print loose"]);
    await storyTime(page, SNAP_AT.pause);
    expect(await shown(page, ".story-scene [data-cam=printer] .word > *")).toEqual(["paused"]);
    await storyTime(page, SNAP_AT.wake);
    expect(await shown(page, ".story-scene [data-cam=kernel] .verdict-box")).toEqual(["confirmation required"]);
    const answer = (await shown(page, ".story-scene [data-cam=client] .said")).join(" ");
    expect(answer).toContain(cancel.result.status);
    expect(answer).not.toContain(nozzle.error.data.name);
  });

  test("changes only transforms and opacity while it plays", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    await storyTime(page, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    const end = await total(page);
    for (let t = 0; t <= end; t += 13) await storyTime(page, t);
    expect(await layouts()).toBe(before);
  });

  test("with reduced motion it is a list of the same steps", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-camera", "");
    await expect(page.locator(".story-scene")).toBeHidden();
    const steps = page.locator(".story-list > li");
    await expect(steps).toHaveCount(11);
    await expect(steps.first()).toBeVisible();
    await expect(page.locator(".story-list .story-snap").first()).toBeVisible();
    const list = page.locator(".story-list");
    await expect(list).toContainText(nb(degrees(nozzle)));
    await expect(list).toContainText(nozzle.error.data.name);
    await expect(list).toContainText(cancel.result.status);
    await expect(list).toContainText("confirmation required");
  });

  test("fits a phone's screen and never scrolls sideways", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    const end = await total(page);
    for (const t of [0, SNAP_AT.watch, SNAP_AT.look, SNAP_AT.warm, SNAP_AT.hot, SNAP_AT.pause, SNAP_AT.wake, end]) {
      await storyTime(page, t);
      const box = await page.locator(".story-stage").boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(844 + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    }
    await storyTime(page, SNAP_AT.look);
    const camera = await page.locator(".story-scene [data-cam=camera]").boundingBox();
    expect(camera!.x).toBeGreaterThanOrEqual(0);
    expect(camera!.x + camera!.width).toBeLessThanOrEqual(390);
  });
});
