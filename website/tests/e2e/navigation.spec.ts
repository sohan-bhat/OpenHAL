import { expect, test } from "@playwright/test";

interface Rule {
  source?: string;
  where: { and: Array<{ href_matches?: string; not?: { selector_matches: string } }> };
  eagerness: string;
}

test.describe("pages load ahead of a click", () => {
  test("every page asks the browser to prerender links on intent, and only prefetches the Playground", async ({ page }) => {
    for (const path of ["/", "/docs/", "/spec/v0.1/basic/messages/", "/404.html"]) {
      await page.goto(path);
      const rules = await page.locator('script[type="speculationrules"]').evaluateAll((scripts) => scripts.map((script) => JSON.parse(script.textContent ?? "{}")));
      expect(rules, path).toHaveLength(1);
      const { prerender, prefetch } = rules[0] as { prerender: Rule[]; prefetch: Rule[] };
      for (const rule of [...prerender, ...prefetch]) {
        expect(rule.eagerness).toBe("moderate");
        expect(rule.where.and[0].href_matches).toBe("/*");
        for (const away of ["/pagefind/", "/captures/", "/og/", "[download]", "[target='_blank']", "a[href^='#']"]) expect(rule.where.and[1].not!.selector_matches).toContain(away);
      }
      expect(prerender[0].where.and[1].not!.selector_matches).toContain("/spec/playground/");
      expect(prefetch[0].where.and[1].not!.selector_matches).not.toContain("/spec/playground/");
    }
  });

  test("pointing at a link fetches its page, and the Playground's kernel waits for a click", async ({ page, context, browserName }) => {
    test.skip(browserName !== "chromium", "speculation rules are a Chromium feature, Firefox is checked below");
    const fetched: string[] = [];
    context.on("request", (request) => fetched.push(new URL(request.url()).pathname));
    const cdp = await context.newCDPSession(page);
    const ready = new Set<string>();
    cdp.on("Preload.prefetchStatusUpdated", (event: { key: { url: string }; status: string }) => {
      if (event.status === "Ready" || event.status === "Success") ready.add(new URL(event.key.url).pathname);
    });
    await cdp.send("Preload.enable");
    await page.goto("/docs/");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Drivers", exact: true }).hover();
    await expect.poll(() => ready.has("/drivers/"), { timeout: 5000 }).toBe(true);
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Playground", exact: true }).hover();
    await expect.poll(() => ready.has("/spec/playground/"), { timeout: 5000 }).toBe(true);
    await page.waitForTimeout(500);
    expect(fetched.filter((path) => /\/_astro\/Playground\./.test(path))).toEqual([]);
  });

  test("without speculation rules, pointing at a link prefetches its page with Astro's prefetch", async ({ page, browserName }) => {
    test.skip(browserName !== "firefox", "Firefox has no speculation rules");
    await page.goto("/docs/");
    expect(await page.evaluate(() => Boolean(HTMLScriptElement.supports?.("speculationrules")))).toBe(false);
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Drivers", exact: true }).hover();
    await expect(page.locator('link[rel="prefetch"][href$="/drivers/"]')).toHaveCount(1, { timeout: 5000 });
    await page.locator("main").getByRole("link", { name: "Quickstart" }).first().focus();
    await expect(page.locator('link[rel="prefetch"][href$="/docs/quickstart/"]')).toHaveCount(1, { timeout: 5000 });
  });
});
