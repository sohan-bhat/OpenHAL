import { expect, test } from "@playwright/test";

test.describe("site chrome", () => {
  test("every main navigation link opens its section and marks it current", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator(".desktop-nav");
    const links = await nav.getByRole("link").evaluateAll((items) =>
      items.map((item) => ({ label: item.textContent!.trim(), href: item.getAttribute("href")! })),
    );
    expect(links.map((link) => link.label)).toEqual(["Overview", "Docs", "Specification", "Playground", "Drivers", "Device Library", "GitHub"]);
    for (const link of links) {
      if (link.href.startsWith("http")) {
        expect(link.href).toBe("https://github.com/sohan-bhat/OpenHAL");
        continue;
      }
      await page.goto("/404.html");
      await page.locator(".desktop-nav").getByRole("link", { name: link.label, exact: true }).click();
      await expect(page.locator(".desktop-nav").getByRole("link", { name: link.label, exact: true })).toHaveAttribute("aria-current", "page");
      await expect(page.locator(".desktop-nav [aria-current]")).toHaveCount(1);
    }
  });

  test("SDKs and the Inspector sit under Docs, which stays current on their pages", async ({ page }) => {
    for (const path of ["/sdks/", "/inspector/"]) {
      await page.goto(path);
      await expect(page.locator(".desktop-nav [aria-current]")).toHaveText("Docs");
    }
    await page.goto("/docs/");
    await expect(page.locator("main")).toContainText("SDKs and Inspector");
    await expect(page.locator("main a[href='/sdks/']").first()).toBeVisible();
    await expect(page.locator("main a[href='/inspector/']").first()).toBeVisible();
  });

  test("the nav highlight has one view transition name on every page", async ({ page }) => {
    for (const path of ["/", "/docs/", "/spec/latest/", "/spec/playground/", "/drivers/", "/library/", "/sdks/"]) {
      await page.goto(path);
      const names = await page.evaluate(() =>
        [...document.querySelectorAll<HTMLElement>("*")].map((el) => getComputedStyle(el).viewTransitionName).filter((name) => name && name !== "none"),
      );
      expect(names.filter((name) => name === "nav-pill")).toHaveLength(1);
      expect(new Set(names).size).toBe(names.length);
      await expect(page.locator(".desktop-nav [aria-current] .nav-pill")).toHaveCount(1);
    }
  });

  test("a page turn moves the way the nav goes, and only for nav links", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "cross-document view transitions are a Chromium feature");
    const turn = () => page.evaluate(() => document.documentElement.dataset.turn ?? null);
    await page.goto("/drivers/");
    await page.locator(".desktop-nav").getByRole("link", { name: "Device Library", exact: true }).click();
    await expect(page).toHaveURL(/\/library\/$/);
    expect(await turn()).toBe("forward");
    await page.waitForTimeout(500);
    await page.locator(".desktop-nav").getByRole("link", { name: "Specification", exact: true }).click();
    await expect(page).toHaveURL(/\/spec\//);
    expect(await turn()).toBe("backward");
    await page.goto("/");
    await page.getByRole("link", { name: "Send the requests in your browser" }).click();
    await expect(page).toHaveURL(/\/spec\/playground\/$/);
    expect(await turn()).toBeNull();
    await page.goBack();
    expect(await turn()).toBeNull();
  });

  test("the overview's try section leads to the playground", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Send the requests in your browser" }).click();
    await expect(page).toHaveURL(/\/spec\/playground\/$/);
    await expect(page.locator("h1")).toHaveText("Playground");
  });

  test("the overview's one call to action goes to the three commands", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Get started" }).click();
    await expect(page).toHaveURL(/#try$/);
    await expect(page.locator("#try figure[data-tested]")).toBeInViewport();
  });

  test("the wordmark goes to the overview", async ({ page }) => {
    await page.goto("/drivers/");
    await page.getByRole("link", { name: "OpenHAL overview" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator("h1")).toHaveText("OpenHAL");
  });

  test("the phone menu opens and navigates", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator(".desktop-nav")).toBeHidden();
    await page.locator(".mobile-nav summary").click();
    await page.locator(".mobile-nav").getByRole("link", { name: "Device Library" }).click();
    await expect(page).toHaveURL(/\/library\/$/);
  });

  test("the footer links to the repository", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("contentinfo").getByRole("link", { name: "Source on GitHub" })).toHaveAttribute("href", "https://github.com/sohan-bhat/OpenHAL");
  });
});

test.describe("documentation chrome", () => {
  test("the sidebar, outline, heading anchors and pager all go somewhere real", async ({ page }) => {
    await page.goto("/docs/quickstart/");
    await page.locator(".side-desktop").getByRole("link", { name: "Concepts" }).click();
    await expect(page).toHaveURL(/\/docs\/concepts\/$/);

    await page.goto("/spec/2026-10-24/basic/messages/");
    const outline = page.locator("aside.outline a").first();
    const target = (await outline.getAttribute("href"))!;
    await outline.click();
    await expect(page).toHaveURL(new RegExp(`${target}$`));
    await expect(page.locator(target)).toBeAttached();

    const anchor = page.locator("h2 a.heading-link").nth(1);
    const hash = (await anchor.getAttribute("href"))!;
    await anchor.click();
    await expect(page).toHaveURL(new RegExp(`${hash}$`));

    const pager = page.getByRole("navigation", { name: "Previous and next" });
    const next = pager.locator("a.next");
    const nextTitle = (await next.locator("span").last().textContent())!.trim();
    await next.click();
    await expect(page.locator("h1")).toHaveText(new RegExp(`^\\d+(\\.\\d+)* ${nextTitle}$`));
    await page.getByRole("navigation", { name: "Previous and next" }).locator("a.prev").click();
    await expect(page.locator("h1")).toHaveText("3.3 Messages");
  });

  test("the version picker lists each dated version and opens it", async ({ page }) => {
    await page.goto("/spec/2026-10-24/basic/messages/");
    await page.locator(".version-button").click();
    const version = page.locator("#version-menu").getByRole("link").first();
    await expect(version).toHaveAttribute("href", /^\/spec\/\d{4}-\d{2}-\d{2}\//);
    await version.click();
    await expect(page).toHaveURL(/\/spec\/\d{4}-\d{2}-\d{2}\//);
  });

  test("the phone section menu and outline open and navigate", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/docs/quickstart/");
    await page.locator(".side-menu summary").first().click();
    await page.locator("#side-nav").getByRole("link", { name: "FAQ" }).click();
    await expect(page).toHaveURL(/\/docs\/faq\/$/);
    await page.goto("/docs/quickstart/");
    await page.locator(".outline-mobile summary").click();
    await page.locator(".outline-mobile").getByRole("link", { name: "Stop" }).click();
    await expect(page).toHaveURL(/#stop$/);
  });

  test("a copy button copies its block", async ({ page, browserName, context }) => {
    test.skip(browserName !== "chromium", "clipboard permissions are a Chromium feature here");
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/library/scpi-rigol-dp832/");
    const button = page.getByRole("button", { name: "Copy code" }).first();
    await button.click();
    await expect(button).toHaveText("Copied");
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("id: rigol-dp832");
  });
});

test.describe("catalog filters", () => {
  test("each driver filter narrows the table and an impossible search says so", async ({ page }) => {
    await page.goto("/drivers/");
    const all = await page.locator("[data-driver]").count();
    for (const [label, option] of [["tier", "Tier 2"], ["conformance", "core"], ["hazard", "high"]] as const) {
      const select = page.locator(`select[name="${label}"]`);
      await select.selectOption({ label: option });
      const shown = await page.locator("[data-driver]:visible").count();
      expect(shown, label).toBeGreaterThan(0);
      expect(shown, label).toBeLessThan(all);
      await select.selectOption("");
    }
    await page.getByLabel("Filter", { exact: true }).fill("scpi");
    await expect(page.locator("[data-driver]:visible")).toHaveCount(1);
    await page.getByLabel("Filter", { exact: true }).fill("no such driver");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await expect(page.locator("[data-shown]")).toHaveText(`0 of ${all} drivers.`);
  });

  test("a filter is drawn only when it has more than one value", async ({ page }) => {
    await page.goto("/drivers/");
    for (const select of await page.locator("[data-filters] select").all()) {
      expect(await select.locator("option").count()).toBeGreaterThan(2);
    }
  });
});

test.describe("playground controls", () => {
  test("the example picker opens on the printer and loads the desk fan too", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const picker = page.locator(".example select");
    await expect(picker).toHaveValue(/printer/);
    await picker.selectOption({ label: "spec/examples/desk-fan-confirmed.hal.yaml" });
    await expect(page.getByLabel("Device file YAML")).toHaveValue(/fan_speed/);
    await expect(page.getByRole("button", { name: "Send hal/write" })).toBeEnabled();
  });

  test("the client picker changes who sends, and a read-only agent is refused", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const as = page.locator(".request select").nth(0);
    const options = await as.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(1);
    const reader = options.find((option) => /read/i.test(option))!;
    await as.selectOption({ label: reader });
    await page.getByLabel("Value").fill("240 degC");
    await page.getByRole("button", { name: /^Send hal\// }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("error");
  });

  test("Stop refuses every request until a person types unlock", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await expect(page.locator(".stop-area .status.blocked")).toHaveText("stopped");
    await page.getByRole("button", { name: "Pause the print" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("STOPPED");
    await page.getByLabel("Type unlock to lift the stop").fill("unlock");
    await page.getByRole("button", { name: "Unlock" }).click();
    await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
  });

  test("a person can reject a request that waits for confirmation", async ({ page }) => {
    await page.goto("/spec/playground/?example=grbl-laser");
    await page.getByLabel("Simulated reading for door_closed").fill("true");
    await page.getByLabel("Simulated reading for door_closed").press("Enter");
    await page.getByLabel("Channel or action").selectOption("laser_power");
    await page.waitForTimeout(1000);
    await page.getByLabel("Value").fill("10 %");
    await page.getByRole("button", { name: "Send hal/write" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText('"status": "pending"');
    await page.getByRole("button", { name: "Reject" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("hal/confirmations/reject");
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
  });

  test("the device picker lists the devices in the file", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const device = page.locator(".request select").nth(1);
    await expect(device).toHaveValue("printer");
    expect(await device.locator("option").count()).toBeGreaterThan(0);
  });
});

test.describe("site search", () => {
  test("Ctrl K opens the search, which finds an error code and opens it from the keyboard", async ({ page }) => {
    await page.goto("/drivers/");
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: "Search the site" });
    await expect(dialog).toBeVisible();
    await expect(page.locator("#site-search-input")).toBeFocused();
    await page.locator("#site-search-input").fill("LIMIT_EXCEEDED");
    const results = dialog.locator("a.search-result");
    await expect(results.first()).toBeVisible({ timeout: 15_000 });
    expect(await results.evaluateAll((items) => items.map((item) => item.getAttribute("href")))).toContain("/spec/errors/");
    await expect(dialog.locator("[data-search-status]")).toHaveText(/pages? match/);
    await page.keyboard.press("ArrowDown");
    await expect(results.first()).toBeFocused();
    const target = (await results.first().getAttribute("href"))!;
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`${target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
  });

  test("the header field opens the search, Escape closes it and focus comes back", async ({ page }) => {
    await page.goto("/");
    const field = page.locator(".search-field");
    await expect(field).toContainText("Search...");
    await expect(field.locator(".search-key span:visible")).toHaveCount(1);
    await field.click();
    const dialog = page.getByRole("dialog", { name: "Search the site" });
    await expect(dialog).toBeVisible();
    await page.locator("#site-search-input").fill("print babysitter");
    await expect(dialog.locator("a.search-result").first()).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(field).toBeFocused();
  });

  test("a search with no match says so", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Control+k");
    await page.locator("#site-search-input").fill("zqxjvw");
    await expect(page.locator("[data-search-status]")).toHaveText("No page matches “zqxjvw”.");
    await expect(page.locator("a.search-result")).toHaveCount(0);
  });

  test("on a phone the field is an icon button that opens the same dialog", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await expect(page.locator(".search-field")).toBeHidden();
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Search the site" })).toBeVisible();
    await page.locator("#site-search-input").fill("print babysitter");
    await expect(page.locator("a.search-result").first()).toBeVisible({ timeout: 15_000 });
  });
});
