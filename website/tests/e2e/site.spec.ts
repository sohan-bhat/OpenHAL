import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const recorded = scenarioFrom(readFileSync(scenarioFile, "utf8"));
const firstError = recorded.record.exchanges.find((exchange: any) => exchange.error)?.error as { code: number; message: string; data: { name: string } };

function noErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test.describe("overview", () => {
  test("states the protocol in one sentence and shows the canonical trace", async ({ page }) => {
    const errors = noErrors(page);
    await page.goto("/");
    await expect(page.locator("h1")).toHaveText("An open-source protocol for AI agents to control hardware.");
    const trace = page.locator(".trace").first();
    await expect(trace).toContainText(`error ${firstError.code} ${firstError.data.name}`);
    await expect(trace).toContainText(firstError.message);
    expect(errors).toEqual([]);
  });

  test("the flow diagram explains each part on focus", async ({ page }) => {
    await page.goto("/");
    const part = page.getByRole("button", { name: "Safety kernel" });
    await part.focus();
    await expect(page.locator(".flow-note")).toHaveText("Checks units, range, rate, interlocks and confirmation, in that order.");
    await expect(page.locator(".flow svg.d2-svg > g.flow-active").first()).toBeAttached();
  });

  test("the quickstart is three commands and says what they show", async ({ page }) => {
    await page.goto("/");
    const block = page.locator("figure[data-tested]").first();
    await expect(block).toContainText("git clone https://github.com/sohan-bhat/OpenHAL");
    await expect(block).toContainText("cd OpenHAL");
    await expect(block).toContainText("uv run openhal demo");
    await expect(page.getByText("You'll see the hub refuse")).toBeVisible();
  });

  test("says plainly that OpenHAL is not affiliated with MHS", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("not affiliated with Anthropic or MHS").first()).toBeVisible();
  });
});

test.describe("specification", () => {
  test("/spec/ goes to the latest dated version, which has a version switcher", async ({ page }) => {
    await page.goto("/spec/");
    await expect(page).toHaveURL(/\/spec\/latest\/$/);
    await expect(page.locator(".switcher summary:visible").first()).toHaveText(/^\s*Version\s+\d{4}-\d{2}-\d{2}\s+latest\s*$/);
    await page.getByRole("link", { name: "Changelog" }).first().click();
    await expect(page.locator("h1")).toHaveText("Changelog");
  });

  test("dated pages have an outline, heading anchors and an edit link", async ({ page }) => {
    await page.goto("/spec/2026-10-24/basic/messages/");
    await expect(page.locator("h1")).toHaveText("Messages");
    await expect(page.locator("aside.outline")).toBeAttached();
    await expect(page.locator("h2 a.heading-link").first()).toHaveAttribute("href", /^#/);
    await expect(page.getByRole("link", { name: "Edit on GitHub" })).toHaveAttribute("href", /\/edit\/main\/spec\/2026-10-24\/basic\/messages\.md$/);
    await expect(page.locator("figure.trace-code svg.trace-arrow").first()).toBeVisible();
  });

  test("defined terms link to the glossary", async ({ page }) => {
    await page.goto("/docs/concepts/");
    await page.getByRole("link", { name: "Safety Kernel", exact: true }).first().click();
    await expect(page).toHaveURL(/\/spec\/glossary\/#term-safety-kernel$/);
    await expect(page.locator("#term-safety-kernel")).toContainText("Safety Kernel");
  });
});

test.describe("playground", () => {
  test("validates live and shows a problem with its place", async ({ page }) => {
    const errors = noErrors(page);
    await page.goto("/spec/playground/");
    const editor = page.getByLabel("Device file YAML");
    await expect(page.locator("#pg-problems")).toContainText("valid");
    await editor.fill("device: Fan\nconnect: { mock: fan }\nwrite:\n  speed: { unit: percent, min: 0 }\n");
    await expect(page.locator("#pg-problems")).toContainText("Number values need both min and max.");
    expect(errors).toEqual([]);
  });

  test("opens on the recorded scenario and answers it as the hub did", async ({ page }) => {
    await page.goto("/spec/playground/");
    const send = page.getByRole("button", { name: /^Send hal\// });
    await send.click();
    const latest = page.locator(".exchanges > li").first();
    await expect(latest).toContainText(`error ${firstError.code} ${firstError.data.name}`);
    await page.getByLabel("Simulated reading for tank").fill("ok");
    await page.getByLabel("Simulated reading for tank").press("Enter");
    await page.getByLabel("Value").fill("duration=20 s");
    await send.click();
    await expect(page.locator(".exchanges > li").first()).toContainText('"status": "done"');
  });

  test("answers an over-limit write as the hub does", async ({ page }) => {
    await page.goto("/spec/playground/?example=desk-fan-confirmed");
    const send = page.getByRole("button", { name: "Send hal/write" });
    await expect(send).toBeEnabled();
    await page.getByLabel("Value").fill("150 %");
    await send.click();
    const latest = page.locator(".exchanges > li").first();
    await expect(latest).toContainText("hal/write");
    await expect(latest).toContainText("error -32010 LIMIT_EXCEEDED");
    await expect(latest).toContainText("fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)");
  });

  test("a dry run reports the decision with its registry error", async ({ page }) => {
    await page.goto("/spec/playground/?example=desk-fan-confirmed");
    await expect(page.getByRole("button", { name: "Dry run" })).toBeEnabled();
    await page.getByLabel("Value").fill("150 %");
    await page.getByRole("button", { name: "Dry run" }).click();
    const latest = page.locator(".exchanges > li").first();
    await expect(latest).toContainText("hal/dryRun");
    await expect(latest).toContainText("LIMIT_EXCEEDED");
  });

  test("a high hazard write waits for a person, who approves it", async ({ page }) => {
    await page.goto("/spec/playground/?example=grbl-laser");
    await expect(page.getByRole("button", { name: "Send hal/write" })).toBeEnabled();
    await page.getByLabel("Simulated reading for door_closed").fill("true");
    await page.getByLabel("Simulated reading for door_closed").press("Enter");
    await page.getByLabel("Channel or action").selectOption("laser_power");
    await page.waitForTimeout(1000);
    await page.getByLabel("Value").fill("10 %");
    await page.getByRole("button", { name: "Send hal/write" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText('"status": "pending"');
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("hal/confirmations/approve");
    await expect(page.locator(".exchanges > li").first()).toContainText('"status": "done"');
  });
});

test.describe("catalog pages", () => {
  test("drivers filter by tier and never claim hardware verification", async ({ page }) => {
    await page.goto("/drivers/");
    await expect(page.getByText("verified on hardware")).toHaveCount(0);
    const all = await page.locator("[data-driver]").count();
    expect(all).toBeGreaterThan(1);
    await page.getByLabel("Tier").selectOption({ label: "Tier 3" });
    const shown = await page.locator("[data-driver]:visible").count();
    expect(shown).toBeLessThan(all);
    await expect(page.locator("[data-shown]")).toHaveText(`${shown} of ${all} drivers.`);
  });

  test("the driver counts leave the tier 0 reference driver out", async ({ page }) => {
    const catalog = JSON.parse(readFileSync(fileURLToPath(new URL("../../../drivers/catalog.json", import.meta.url)), "utf8")) as {
      drivers: Array<{ name: string; tier: number; status: string }>;
    };
    const devices = catalog.drivers.filter((driver) => driver.tier >= 1);
    const tested = devices.filter((driver) => driver.status === "implemented").length;
    await page.goto("/");
    await expect(page.locator("p.summary")).toContainText(`${tested} drivers tested on simulator`);
    await expect(page.locator(".groups")).not.toContainText("mock");
    await page.goto("/drivers/");
    await expect(page.locator("[data-shown]")).toHaveText(`${devices.length} drivers.`);
    await expect(page.locator("[data-driver]")).toHaveCount(devices.length);
    for (const driver of catalog.drivers.filter((item) => item.tier === 0)) {
      await expect(page.locator("[data-reference]").filter({ hasText: driver.name })).toContainText("reference");
    }
  });

  test("drivers and the library sit in the same page container as the specification", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const left = async (path: string) => {
      await page.goto(path);
      return page.locator("main h1").evaluate((heading) => Math.round(heading.getBoundingClientRect().left));
    };
    const spec = await left("/spec/2026-10-24/basic/messages/");
    for (const path of ["/drivers/", "/drivers/mock/", "/library/", "/library/scpi-rigol-dp832/", "/docs/quickstart/"]) {
      expect(await left(path), path).toBe(spec);
    }
  });

  test("each driver has its own page", async ({ page }) => {
    await page.goto("/drivers/mock/");
    await expect(page.locator("h1")).toContainText("mock");
  });

  test("the library searches its files and never shows an unconfirmed file as confirmed", async ({ page }) => {
    await page.goto("/library/");
    const rows = page.locator("[data-entry]");
    const all = await rows.count();
    expect(all).toBeGreaterThan(30);
    await expect(page.locator("[data-shown]")).toHaveText(`${all} device files.`);
    await page.getByLabel("Filter", { exact: true }).fill("rigol");
    await expect(page.locator("[data-shown]")).toHaveText(`2 of ${all} device files.`);
    await page.getByLabel("Filter", { exact: true }).fill("no such device");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await expect(page.getByRole("article").getByRole("link", { name: "How the library works" })).toHaveAttribute("href", "/docs/library/");
    await page.goto("/library/scpi-keysight-34461a/");
    await expect(page.locator(".facts")).toContainText("unconfirmed");
    await expect(page.locator(".facts")).toContainText("This file only reads.");
    await page.goto("/library/scpi-rigol-dp832/");
    await expect(page.locator(".facts")).toContainText("set_ch1 (action)");
    await expect(page.getByRole("table", { name: "Actions" })).toContainText("volts 0 to 5 V, step 0.01");
  });

  test("the Python reference is generated from docstrings", async ({ page }) => {
    await page.goto("/sdks/python/reference/");
    await expect(page.getByRole("heading", { name: /connect/ }).first()).toBeVisible();
  });
});

test.describe("site", () => {
  test("docs render from the repository with tested snippets marked", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    await expect(page.locator("h1")).toHaveText("Quickstart");
    await expect(page.locator("figure[data-tested]").first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Previous and next" }).getByRole("link").first()).toBeVisible();
  });

  test("copy buttons copy only the commands", async ({ page, browserName, context }) => {
    test.skip(browserName !== "chromium", "clipboard permissions are a Chromium feature here");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/docs/quickstart/");
    await page.locator("figure[data-tested]").first().getByRole("button", { name: "Copy code" }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toBe("git clone https://github.com/sohan-bhat/OpenHAL\ncd OpenHAL\nuv run openhal demo");
  });

  test("every page in the sitemap has its Open Graph image", async ({ request, browserName }) => {
    test.skip(browserName !== "chromium", "one pass is enough");
    const sitemap = await (await request.get("/sitemap-0.xml")).text();
    const pages = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname);
    expect(pages.length).toBeGreaterThan(30);
    for (const path of [...pages, "/404.html"]) {
      const html = await (await request.get(path)).text();
      const image = /<meta property="og:image" content="([^"]+)"/.exec(html)?.[1];
      expect(image, path).toBeTruthy();
      const response = await request.get(new URL(image!).pathname);
      expect(response.status(), `${path} -> ${image}`).toBe(200);
      expect(response.headers()["content-type"]).toContain("image/png");
    }
  });

  test("an unknown address answers UNKNOWN_TARGET", async ({ page }) => {
    const response = await page.goto("/no-such-page/");
    expect(response?.status()).toBe(404);
    await expect(page.locator("h1")).toHaveText("Page not found");
    await expect(page.locator(".trace")).toContainText("error -32004 UNKNOWN_TARGET");
    await expect(page.locator(".trace .method")).toHaveText("hal/devices/describe");
    await expect(page.locator(".trace .payload")).toHaveText('{ "device": "/no-such-page/" }');
  });

  test("nothing scrolls sideways at 1280 px", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    for (const path of ["/sdks/", "/sdks/python/", "/sdks/python/reference/", "/spec/playground/", "/spec/2026-10-24/basic/messages/", "/library/scpi-rigol-dp832/"]) {
      await page.goto(path);
      const wide = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("pre, textarea, .table-wrap, .trace")]
          .filter((element) => element.getClientRects().length && element.scrollWidth > element.clientWidth + 1)
          .map((element) => `${element.tagName} ${element.scrollWidth}>${element.clientWidth}`),
      );
      expect(wide, path).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth), path).toBeLessThanOrEqual(1280);
    }
  });

  test("the playground's As picker shows its whole label", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/spec/playground/");
    const fits = await page.locator(".request select").first().evaluate((select: HTMLSelectElement) => {
      const probe = document.createElement("span");
      probe.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font:${getComputedStyle(select).font}`;
      probe.textContent = select.selectedOptions[0].textContent;
      document.body.append(probe);
      const width = probe.getBoundingClientRect().width;
      probe.remove();
      return width + 40 <= select.clientWidth;
    });
    expect(fits).toBe(true);
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
