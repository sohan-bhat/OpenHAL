import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const heading = "h1#_top,:where(h2,h3)[id]";
const script = readFileSync(fileURLToPath(new URL("../../node_modules/@astrojs/starlight/dist/components-internals/TableOfContents/starlight-toc.js", import.meta.url)), "utf8");
const start = script.indexOf("const toObserve");
const shipped = [...script.slice(start, script.indexOf("].join()", start)).matchAll(/`([^`]*)`/g)].map((match) => match[1].replaceAll("${this.tocHeadingSelector}", heading)).join();
const original = [`main :where(${heading})`, `main :where(${heading}, .sl-heading-wrapper) ~ *:not(:has(${heading}))`, `main .sl-markdown-content > *:not(:has(${heading}))`, `main > *:not(:has(${heading}))`].join();

test.describe("the outline", () => {
  for (const path of ["/spec/v0.1/schema/", "/spec/v0.1/basic/messages/", "/docs/quickstart/", "/docs/architecture/", "/drivers/moonraker/"]) {
    test(`observes exactly the elements Starlight's own selectors find, in the same order, on ${path}`, async ({ page }) => {
      await page.goto(path);
      const found = await page.evaluate(([patched, starlight]) => {
        const ours = [...document.querySelectorAll(patched)];
        const theirs = [...document.querySelectorAll(starlight)];
        return { count: theirs.length, same: ours.length === theirs.length && ours.every((node, index) => node === theirs[index]) };
      }, [shipped, original]);
      expect(found.count).toBeGreaterThan(1);
      expect(found.same).toBe(true);
    });
  }

  test("marks the section a reader jumps to on a desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/spec/v0.1/schema/");
    const link = page.locator('starlight-toc a[href="#confirmationrequest"]');
    await link.click();
    await expect(link).toHaveAttribute("aria-current", "true");
    await expect(page.locator("starlight-toc a[aria-current]")).toHaveCount(1);
  });

  test("names the section a reader is in at the top of a phone's outline", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/spec/v0.1/schema/#writeparams");
    await expect(page.locator("mobile-starlight-toc .display-current")).toHaveText(/\sWriteParams\s*$/);
    await page.locator("mobile-starlight-toc summary").click();
    await page.locator('mobile-starlight-toc a[href="#readparams"]').click();
    await expect(page.locator("#starlight__mobile-toc")).not.toHaveAttribute("open");
    await expect(page.locator("mobile-starlight-toc .display-current")).toHaveText(/\sReadParams\s*$/);
  });
});
