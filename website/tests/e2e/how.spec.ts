import { expect, test, type Page } from "@playwright/test";
import { HOW_CHART, chartLead, pathText } from "../../src/lib/story/how";

/** The chart image a person sees, its file and whether the file loaded. */
const seen = (page: Page) =>
  page.locator("#how .how-chart img").evaluateAll((images) =>
    images
      .filter((img) => (img as HTMLImageElement).getClientRects().length > 0)
      .map((img) => {
        const image = img as HTMLImageElement;
        const box = image.getBoundingClientRect();
        return { file: new URL(image.currentSrc).pathname.split("/").pop(), loaded: image.complete && image.naturalWidth > 0, left: box.left, right: box.right, width: box.width };
      }),
  );

async function showChart(page: Page): Promise<void> {
  await page.locator("#how .how-chart").scrollIntoViewIfNeeded();
  await expect.poll(async () => (await seen(page)).every((image) => image.loaded) && (await seen(page)).length === 1).toBe(true);
}

test.describe("How it works", () => {
  for (const scheme of ["light", "dark"] as const) {
    for (const form of [
      { width: 1440, height: 900, shape: "wide" },
      { width: 768, height: 1024, shape: "narrow" },
      { width: 390, height: 844, shape: "narrow" },
      { width: 360, height: 700, shape: "narrow" },
    ]) {
      test(`shows the ${form.shape} chart in the ${scheme} theme at ${form.width} px, inside the screen`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme });
        await page.setViewportSize({ width: form.width, height: form.height });
        await page.goto("/");
        await showChart(page);
        const [image] = await seen(page);
        expect(image.file).toBe(`how-it-works-${form.shape}-${scheme}.png`);
        expect(image.left).toBeGreaterThanOrEqual(0);
        expect(image.right).toBeLessThanOrEqual(form.width);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(form.width);
      });
    }
  }

  test("follows the theme picker, not only the system", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.addInitScript(() => localStorage.setItem("starlight-theme", "dark"));
    await page.goto("/");
    await showChart(page);
    expect((await seen(page))[0].file).toBe("how-it-works-wide-dark.png");
  });

  test("keeps its heading and names all three paths for screen readers", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 2, name: "How it works" })).toBeVisible();
    const caption = page.locator("#how figcaption");
    await expect(caption.locator("p")).toHaveText(chartLead());
    await expect(caption.locator("li")).toHaveText(HOW_CHART.paths.map(pathText));
    await expect(page.locator("#how .how-chart img")).toHaveCount(2);
    for (const img of await page.locator("#how .how-chart img").all()) await expect(img).toHaveAttribute("alt", "");
  });

  test("stays still, with no pinned stage, Skip or Smooth scrolling switch", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("switch", { name: "Smooth scrolling" })).toHaveCount(0);
    await expect(page.locator("#how").getByRole("link", { name: /Skip/ })).toHaveCount(0);
    expect(await page.locator("#how *").evaluateAll((items) => items.filter((el) => ["sticky", "fixed"].includes(getComputedStyle(el).position)).length)).toBe(0);
    await expect(page.locator("#how script, #how + script")).toHaveCount(0);
  });

  test("ends with a link to the full example", async ({ page }) => {
    await page.goto("/");
    const link = page.getByRole("link", { name: "See the full example: an agent watching a 3D print overnight" });
    await expect(link).toHaveAttribute("href", "/docs/examples/3d-print-watch/");
    await link.click();
    await expect(page.locator("h1")).toHaveText("Example: an agent watching a 3D print");
  });
});
