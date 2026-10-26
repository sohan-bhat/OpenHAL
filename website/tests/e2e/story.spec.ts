import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";
import { SNAP_AT } from "../../src/lib/story/timeline";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const [tooLong, empty, watered] = scenarioFrom(readFileSync(scenarioFile, "utf8")).record.exchanges as any[];
const nb = (text: string) => text.replace(/(\d) /g, "$1 ");

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

test.describe("the landing story", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("pins its stage under the header and moves its camera with the scroll", async ({ page }) => {
    await page.goto("/");
    const story = page.locator("[data-story]");
    await expect(story).toHaveAttribute("data-camera", "");
    await expect(story).toHaveAttribute("data-ready", "");
    await storyTime(page, 0);
    const wide = await page.locator(".story-scene").evaluate((scene) => scene.style.transform);
    await storyTime(page, SNAP_AT.check);
    const close = await page.locator(".story-scene").evaluate((scene) => scene.style.transform);
    expect(close).toMatch(/^translate\(.+\) scale\(.+\)$/);
    expect(close).not.toBe(wide);
    const top = await page.locator(".story-stage").evaluate((stage) => stage.getBoundingClientRect().top);
    expect(top).toBe(await page.locator(".site-header").evaluate((header) => (header as HTMLElement).offsetHeight));
  });

  test("plays the scenario's three answers on the stage", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, SNAP_AT.check);
    expect(await shown(page, ".story-scene [data-cam=kernel] .verdict-box")).toEqual([tooLong.error.data.name]);
    await storyTime(page, SNAP_AT.reply);
    expect((await shown(page, ".story-scene [data-cam=client] .said")).join(" ")).toContain(nb(tooLong.error.message.split(" (")[0]));
    await storyTime(page, SNAP_AT.hold);
    expect(await shown(page, ".story-scene [data-cam=kernel] .verdict-box")).toEqual([empty.error.data.name]);
    await storyTime(page, SNAP_AT.soil);
    expect(await shown(page, ".story-scene [data-cam=device] .figure > *")).toEqual([`${watered.soil_moisture.after.value} %`]);
    await storyTime(page, SNAP_AT.done);
    const answer = (await shown(page, ".story-scene [data-cam=client] .said")).join(" ");
    expect(answer).toContain(watered.result.status);
    expect(answer).not.toContain(tooLong.error.data.name);
  });

  test("changes only transforms and opacity while it plays", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    await storyTime(page, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    for (let t = 0; t <= 520; t += 13) await storyTime(page, t);
    expect(await layouts()).toBe(before);
  });

  test("with reduced motion it is a list of the same steps", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-camera", "");
    await expect(page.locator(".story-scene")).toBeHidden();
    const steps = page.locator(".story-list > li");
    await expect(steps).toHaveCount(10);
    await expect(steps.first()).toBeVisible();
    await expect(steps.first()).toContainText(nb(`${tooLong.request.params.args.duration.value} s`));
    await expect(page.locator(".story-list .story-snap").first()).toBeVisible();
    await expect(page.locator(".story-list")).toContainText(empty.error.data.name);
    await expect(page.locator(".story-list")).toContainText(`${watered.soil_moisture.before.value} % to ${watered.soil_moisture.after.value} %`);
  });

  test("fits a phone's screen and never scrolls sideways", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    for (const t of [0, SNAP_AT.ask, SNAP_AT.check, SNAP_AT.hold, SNAP_AT.soil, SNAP_AT.done, 520]) {
      await storyTime(page, t);
      const box = await page.locator(".story-stage").boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(844 + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    }
    await storyTime(page, SNAP_AT.ask);
    const client = await page.locator(".story-scene [data-cam=client]").boundingBox();
    expect(client!.x).toBeGreaterThanOrEqual(0);
    expect(client!.x + client!.width).toBeLessThanOrEqual(390);
  });
});
