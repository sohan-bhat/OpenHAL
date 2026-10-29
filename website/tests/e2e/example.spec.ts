import { expect, test, type Page } from "@playwright/test";
import { EXAMPLE } from "../../src/lib/story/example";
import { IDS, nb, storyFacts, storyLines, type Lifeline, type Sending } from "../../src/lib/story/facts";
import { auditLog, messages } from "../../src/lib/story/messages";
import { COUNTED, type StepId } from "../../src/lib/story/script";
import { SEEN, storySequence } from "../../src/lib/story/timeline";

const facts = storyFacts();
const lines = storyLines(facts);
const sequence = storySequence(facts);
const flat = (text: string) => text.replace(/\s+/g, " ").trim();
const row = (id: Sending) => sequence.rows.find((item) => item.id === id)!;

const shown = (page: Page, selector: string) =>
  page.evaluate(
    (query) =>
      [...document.querySelectorAll<HTMLElement>(query)]
        .filter((el) => {
          for (let node: HTMLElement | null = el; node && !node.matches("[data-story]"); node = node.parentElement) if (Number(getComputedStyle(node).opacity) < 0.9) return false;
          return el.getClientRects().length > 0;
        })
        .map((el) => el.textContent!.replace(/\s+/g, " ").trim()),
    selector,
  );

/** Where each drawn leg of a row starts and ends, and whether its head shows. */
const legsOf = (page: Page, id: Sending) =>
  page.evaluate((name) => {
    const x = Object.fromEntries([...document.querySelectorAll<HTMLElement>(".story-scene .lifeline")].map((el) => [el.dataset.line!, el.getBoundingClientRect().left + el.getBoundingClientRect().width / 2]));
    const legs = [...document.querySelectorAll<HTMLElement>(`.story-scene .leg[data-row="${name}"]`)].map((leg) => {
      const back = leg.classList.contains("back");
      const line = leg.querySelector<HTMLElement>(".stroke.live .line")!.getBoundingClientRect();
      return { start: back ? leg.getBoundingClientRect().right : leg.getBoundingClientRect().left, tip: back ? line.left - 7 : line.right + 7 };
    });
    return { x, legs };
  }, id);

/** Goes to the step at `index`, from 0, with Next. */
async function stepTo(page: Page, index: number): Promise<void> {
  const next = page.getByRole("button", { name: "Next step" });
  for (let at = await current(page); at < index; at++) await next.click();
  await expect(page.locator(".story-count [data-on]")).toHaveText(`${index + 1} / ${COUNTED.length}`);
  await page.waitForTimeout(1300);
}

const current = async (page: Page) => Number((await page.locator(".story-count [data-on]").textContent())!.split(" / ")[0]) - 1;

test.describe("the full example page", () => {
  test("is titled for the example and listed under Examples in the docs", async ({ page }) => {
    await page.goto(EXAMPLE.href);
    await expect(page.locator("h1")).toHaveText(EXAMPLE.title);
    const sidebar = page.locator("nav.sidebar, .sidebar-content").first();
    await expect(sidebar.getByText("Examples", { exact: true })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: EXAMPLE.link })).toHaveAttribute("aria-current", "page");
    await page.goto("/docs/");
    await expect(page.getByRole("heading", { name: "Examples" })).toBeVisible();
    await expect(page.getByRole("link", { name: EXAMPLE.link }).first()).toHaveAttribute("href", EXAMPLE.href);
  });

  test("is linked from How it works on the home page and from the quickstart", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: "See the full example: an agent watching a 3D print overnight" })).toHaveAttribute("href", EXAMPLE.href);
    await page.goto("/docs/quickstart/");
    await expect(page.locator("main").getByRole("link", { name: "The full example" })).toHaveAttribute("href", EXAMPLE.href);
  });

  test("walks through the nine steps with Previous and Next, one caption at a time", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(EXAMPLE.href);
    const previous = page.getByRole("button", { name: "Previous step" });
    const next = page.getByRole("button", { name: "Next step" });
    await expect(previous).toHaveAttribute("aria-disabled", "true");
    for (const [index, item] of COUNTED.entries()) {
      await stepTo(page, index);
      const id = item.id as Exclude<StepId, "intro">;
      expect(await shown(page, ".story-note"), id).toEqual([flat(nb(lines[id]))]);
      if (index > 0) await expect(page.locator("[data-said]")).toHaveText(`Step ${index + 1} of ${COUNTED.length}. ${flat(nb(lines[id]))}`);
    }
    await expect(next).toHaveAttribute("aria-disabled", "true");
    await next.dispatchEvent("click");
    await expect(page.locator(".story-count [data-on]")).toHaveText(`${COUNTED.length} / ${COUNTED.length}`);
    await next.focus();
    await expect(next).toBeFocused();
    await previous.click();
    await expect(page.locator(".story-count [data-on]")).toHaveText(`${COUNTED.length - 1} / ${COUNTED.length}`);
    await expect.poll(() => shown(page, ".story-note")).toEqual([flat(nb(lines.approve))]);
  });

  test("draws each request as far as the record says it went, and holds the cancel at the hub until the approval", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto(EXAMPLE.href);
    for (const id of ["warm", "hot", "cancel", "approve"] as Sending[]) {
      await stepTo(page, COUNTED.findIndex((item) => item.id === id));
      const { x, legs } = await legsOf(page, id);
      for (const [index, leg] of row(id).legs.entries()) {
        expect(Math.abs(legs[index].start - x[leg.from as Lifeline]), `${id} leg ${index + 1}`).toBeLessThan(2);
        expect(Math.abs(legs[index].tip - x[leg.to as Lifeline]), `${id} leg ${index + 1}`).toBeLessThan(2);
      }
    }
    expect(row("hot").legs.at(-1)!.to).toBe("hub");
    expect(row("cancel").legs.at(-1)!.to).toBe("hub");
    expect(row("approve").legs[0].from).toBe("owner");
    expect(await shown(page, ".story-scene .answer")).toContain(facts.nozzle.refusal.name);
  });

  test("shows the frame each read returned and what the agent saw", async ({ page }) => {
    await page.goto(EXAMPLE.href);
    await stepTo(page, COUNTED.findIndex((item) => item.id === "look"));
    expect(await shown(page, ".cam-seen > *")).toEqual([SEEN.lifting]);
    await stepTo(page, COUNTED.findIndex((item) => item.id === "loose"));
    expect(await shown(page, ".cam-seen > *")).toEqual([SEEN.loose]);
    await expect(page.locator(".cam-note")).toHaveText("Webcam, demo frame");
  });

  test("shows the device file, every request with the hub's answer, and the audit log", async ({ page }) => {
    await page.goto(EXAMPLE.href);
    const file = page.locator("#device-file ~ figure.code-block").first();
    await expect(file).toContainText(`max: ${facts.nozzle.max.split(" ")[0]}`);
    await expect(file).toContainText("confirm: confirm-each-time");
    const sent = messages();
    const items = page.locator(".messages > li");
    await expect(items).toHaveCount(sent.length);
    for (const [index, message] of sent.entries()) {
      const blocks = items.nth(index).locator("figure.code-block pre");
      await expect(blocks).toHaveCount(2);
      expect(JSON.parse((await blocks.nth(0).innerText()).trim())).toEqual(JSON.parse(message.request));
      expect(JSON.parse((await blocks.nth(1).innerText()).trim())).toEqual(JSON.parse(message.response));
    }
    await expect(items.nth(sent.findIndex((message) => message.id === IDS.nozzle))).toContainText(facts.nozzle.refusal.name);
    const audit = auditLog();
    const rows = page.locator("#audit-log ~ .table-wrap tbody tr");
    await expect(rows).toHaveCount(audit.entries.length);
    await expect(rows.first()).toContainText(audit.entries[0].message);
    await expect(rows.locator(".status.blocked")).toHaveText(["blocked"]);
    await expect(page.locator("main")).toContainText(audit.counts);
  });

  test("with reduced motion shows each step at once", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(EXAMPLE.href);
    const next = page.getByRole("button", { name: "Next step" });
    await next.click();
    await next.click();
    const { x, legs } = await legsOf(page, "warm");
    expect(Math.abs(legs.at(-1)!.tip - x.printer)).toBeLessThan(2);
  });

  test("without a script shows the whole run drawn and the list of steps", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(EXAMPLE.href);
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-walk");
    await expect(page.locator(".story-controls")).toBeHidden();
    await expect(page.locator(".story-list > li")).toHaveCount(COUNTED.length);
    await expect(page.locator(".story-list")).toContainText(facts.nozzle.refusal.name);
    expect(await shown(page, ".story-scene .answer")).toEqual(sequence.rows.flatMap((item) => (item.reply ? [item.reply.answer.text] : [])));
    await context.close();
  });

  test("keeps code, YAML and the diagrams out of what search shows", async ({ page }) => {
    await page.goto("/docs/");
    const found = await page.evaluate(async () => {
      const pagefind = await import(/* @vite-ignore */ `${location.origin}/pagefind/pagefind.js`);
      await pagefind.init();
      const out: Record<string, Array<{ url: string; excerpt: string }>> = {};
      for (const term of ["babysit", "LIMIT_EXCEEDED", "abstraction", "provenance"]) {
        const search = await pagefind.search(term);
        out[term] = await Promise.all(search.results.slice(0, 10).map(async (result: { data: () => Promise<{ url: string; excerpt: string }> }) => {
          const data = await result.data();
          return { url: data.url, excerpt: data.excerpt.replace(/<[^>]+>/g, "") };
        }));
      }
      return out;
    });
    for (const [term, results] of Object.entries(found)) {
      for (const result of results.filter((item) => item.url === "/" || item.url === EXAMPLE.href)) {
        expect(result.excerpt, `${term} ${result.url}`).not.toMatch(/provenance: \{|"jsonrpc"|\{ "(method|result|error)"|^\s*device:|\$ uv run/);
        if (result.url === "/") expect(result.excerpt, `${term} on home`).not.toMatch(/gives every device the same interface|9 steps|Skip the demo/);
      }
    }
    expect(found.abstraction.map((result) => result.url)).toContain("/docs/concepts/");
  });
});
