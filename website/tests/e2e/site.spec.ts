import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const steps = JSON.parse(readFileSync(fileURLToPath(new URL("../../src/content/demo/steps.json", import.meta.url)), "utf8"));
const BLOCK_150 = "Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.";

function noErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test.describe("landing page", () => {
  test("the hero shows a real block from the kernel port, before and after scripts run", async ({ page }) => {
    const errors = noErrors(page);
    await page.goto("/");
    await expect(page.locator("h1")).toHaveText("Real hardware for AI agents. Limits set by people.");
    const demo = page.locator("[data-hero-demo]");
    await expect(demo.locator("[data-reason]")).toHaveText(BLOCK_150);
    await expect(demo.getByText("In-browser demo")).toBeVisible();
    await expect(demo.locator("[data-send]")).toBeEnabled();
    expect(errors).toEqual([]);
  });

  test("an agent's writes are checked, and the stop bar stops and lifts", async ({ page }) => {
    await page.goto("/");
    const demo = page.locator("[data-hero-demo]");
    await expect(demo.locator("[data-send]")).toBeEnabled();
    await page.waitForTimeout(2100);
    await demo.getByRole("button", { name: "40 %" }).click();
    await expect(demo.locator("[data-output]")).toContainText("Done. fan_speed is now 40 %.");
    await expect(demo.locator("[data-fan]")).toHaveText("40");
    await demo.getByRole("button", { name: "95 degF" }).click();
    await expect(demo.locator("[data-output]")).toContainText("bad_unit");
    await demo.getByRole("button", { name: "Stop all" }).click();
    await expect(demo.locator("[data-stopped]")).toBeVisible();
    await expect(demo.locator("[data-fan]")).toHaveText("0");
    await demo.getByRole("button", { name: "150 %" }).click();
    await expect(demo.locator("[data-output]")).toContainText("Blocked. The hub is stopped.");
    await demo.getByLabel("Type unlock to lift the stop").fill("open");
    await demo.getByRole("button", { name: "Unlock" }).click();
    await expect(demo.locator("[data-unlock-error]")).toHaveText("Type unlock to confirm.");
    await demo.getByLabel("Type unlock to lift the stop").fill("unlock");
    await demo.getByRole("button", { name: "Unlock" }).click();
    await expect(demo.getByRole("button", { name: "Stop all" })).toBeVisible();
  });

  test("the storyboard shows every step from the real CLI", async ({ page }) => {
    await page.goto("/");
    for (const step of steps) {
      await expect(page.locator(`#demo-${step.id} pre`)).toContainText(step.text.split("\n")[0]);
    }
    await expect(page.locator("#demo-blocked pre")).toContainText(BLOCK_150);
  });

  test("the MHS section says it in three plain sentences", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("MHS is for labs, in a closed preview.")).toBeVisible();
    await expect(page.getByText("OpenHAL is open and works today.").first()).toBeVisible();
    await expect(page.getByText("We plan to be compatible.").first()).toBeVisible();
  });
});

test.describe("playground", () => {
  test("validates live and shows a problem with its place", async ({ page }) => {
    const errors = noErrors(page);
    await page.goto("/playground/");
    const editor = page.getByLabel("Device file YAML");
    await expect(page.locator("#pg-problems")).toContainText("Valid");
    await editor.fill("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: percent, min: 0 }\n");
    await expect(page.locator("#pg-problems")).toContainText("Number values need both min and max.");
    await editor.fill("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: percent, min: 0, max: 50 }\nspeedy: 1\n");
    await expect(page.locator("#pg-problems")).toContainText("Unknown key speedy.");
    expect(errors).toEqual([]);
  });

  test("blocks a write with the hub's code and message", async ({ page }) => {
    await page.goto("/playground/?example=desk-fan-confirmed");
    await expect(page.locator("#pg-problems")).toContainText("Valid");
    const breaker = page.locator(".breaker");
    await expect(breaker.getByRole("button", { name: "Send" })).toBeEnabled();
    await breaker.getByLabel("Value").fill("150 %");
    await breaker.getByRole("button", { name: "Send" }).click();
    await expect(breaker.locator(".log li").first()).toContainText(BLOCK_150);
    await expect(breaker.locator(".log li").first()).toContainText("above_max");
  });

  test("a high hazard write waits for a person, who approves it", async ({ page }) => {
    await page.goto("/playground/?example=grbl-laser");
    await expect(page.locator("#pg-problems")).toContainText("Valid");
    const breaker = page.locator(".breaker");
    await expect(breaker.getByRole("button", { name: "Send" })).toBeEnabled();
    await page.getByLabel("Simulated reading for door_closed").fill("true");
    await page.getByLabel("Simulated reading for door_closed").press("Enter");
    await breaker.getByLabel("Channel or action").selectOption("laser_power");
    // laser_power may move 30 % per second, so give the window a moment to open.
    await page.waitForTimeout(1000);
    await breaker.getByLabel("Value").fill("10 %");
    await breaker.getByRole("button", { name: "Send" }).click();
    await expect(breaker.locator(".log li").first()).toContainText("Waiting for a human to approve write:laser_power on laser.");
    await breaker.getByRole("button", { name: "Approve" }).click();
    await expect(breaker.locator(".log li").first()).toContainText("Done. laser_power is now 10 %.");
  });
});

test.describe("other pages", () => {
  test("supported devices filter by status", async ({ page }) => {
    await page.goto("/devices/");
    const all = await page.locator("[data-driver]").count();
    expect(all).toBeGreaterThan(1);
    await page.getByLabel("Status").selectOption("implemented");
    const shown = await page.locator("[data-driver]:visible").count();
    expect(shown).toBeLessThan(all);
    await expect(page.locator("[data-shown]")).toContainText(`${shown} of ${all} drivers shown.`);
  });

  test("the library explains how to contribute while it is empty", async ({ page }) => {
    await page.goto("/library/");
    await expect(page.getByRole("heading", { name: "No device files yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "The guide" })).toHaveAttribute("href", "/docs/contributing-a-device-file/");
  });

  test("the spec has a version selector and the changelog", async ({ page }) => {
    await page.goto("/spec/");
    const versions = page.getByRole("navigation", { name: "Spec versions" });
    await expect(versions.getByRole("link", { name: /0\.1/ })).toHaveAttribute("aria-current", "page");
    await page.getByRole("link", { name: "Changelog", exact: true }).click();
    await expect(page.locator("h1")).toHaveText("Spec changelog");
  });

  test("docs render from the repository with tested snippets marked", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    await expect(page.locator("h1")).toHaveText("Quickstart");
    await expect(page.locator("figure[data-tested]").first()).toBeVisible();
    await page.goto("/docs/safety/");
    await expect(page.getByRole("heading", { name: "The checks, in order" })).toBeVisible();
  });

  test("every page in the sitemap has its Open Graph image", async ({ request, browserName }) => {
    test.skip(browserName !== "chromium", "one pass is enough");
    const sitemap = await (await request.get("/sitemap-0.xml")).text();
    const pages = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname);
    expect(pages.length).toBeGreaterThan(15);
    for (const path of [...pages, "/404.html"]) {
      const html = await (await request.get(path)).text();
      const image = /<meta property="og:image" content="([^"]+)"/.exec(html)?.[1];
      expect(image, path).toBeTruthy();
      const response = await request.get(new URL(image!).pathname);
      expect(response.status(), `${path} -> ${image}`).toBe(200);
      expect(response.headers()["content-type"]).toContain("image/png");
    }
  });

  test("an unknown address shows the 404 page", async ({ page }) => {
    const response = await page.goto("/no-such-page/");
    expect(response?.status()).toBe(404);
    await expect(page.locator("h1")).toHaveText("Page not found");
  });

  test("keyboard users can skip to the content and see focus", async ({ page, browserName }) => {
    test.skip(browserName === "webkit", "WebKit only tabs to links with the macOS full keyboard setting");
    await page.goto("/docs/");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    const outline = await skip.evaluate((element) => getComputedStyle(element).outlineStyle);
    expect(outline).not.toBe("none");
  });
});
