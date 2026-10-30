import { expect, test, type Page } from "@playwright/test";
import { CAPTIONS, howSteps, type Reply } from "../../src/lib/story/how";

const steps = howSteps();
const flat = (text: string) => text.replace(/\s+/g, " ").trim();

/** Scrolls to the point of How it works where step `step` (from 1) is `along` of the way through. */
async function howAt(page: Page, step: number, along: number): Promise<void> {
  await page.evaluate(
    ([at, count]) => {
      const track = document.querySelector<HTMLElement>(".how-track")!;
      const header = document.querySelector<HTMLElement>("header.header")?.offsetHeight ?? 0;
      let top = 0;
      for (let el: HTMLElement | null = track; el; el = el.offsetParent as HTMLElement | null) top += el.offsetTop;
      const distance = track.offsetHeight - (window.innerHeight - header);
      window.scrollTo({ top: top - header + (at / count) * distance, behavior: "instant" });
    },
    [step - 1 + along, steps.length] as const,
  );
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForTimeout(400);
}

const shown = (page: Page, selector: string) =>
  page.evaluate(
    (query) =>
      [...document.querySelectorAll<HTMLElement>(query)]
        .filter((el) => {
          for (let node: HTMLElement | null = el; node && !node.matches("[data-how]"); node = node.parentElement) if (Number(getComputedStyle(node).opacity) < 0.9) return false;
          return el.getClientRects().length > 0;
        })
        .map((el) => el.textContent!.replace(/\s+/g, " ").trim()),
    selector,
  );

/** The lifelines and arrows of one step's diagram, in px from the left of the page, and how far each arrow has drawn. */
const geometry = (page: Page, index: number) =>
  page.evaluate((at) => {
    const step = document.querySelectorAll<HTMLElement>(".how-step")[at];
    const middle = (el: Element) => el.getBoundingClientRect().left + el.getBoundingClientRect().width / 2;
    const x = Object.fromEntries([...step.querySelectorAll<HTMLElement>(".how-life")].map((el) => [el.dataset.line!, middle(el)]));
    const legs = [...step.querySelectorAll<HTMLElement>(".how-leg")].map((el) => {
      const box = el.getBoundingClientRect();
      const stroke = el.querySelector<HTMLElement>(".how-line, .how-dash")!;
      const drawn = stroke.getBoundingClientRect().width / Math.max(1, stroke.offsetWidth);
      const clip = getComputedStyle(stroke).clipPath;
      const hidden = clip.startsWith("inset") ? parseFloat(clip.replace(/^inset\(/, "").split(" ")[3] ?? "0") / 100 : 0;
      return {
        row: Number(el.dataset.row),
        from: el.dataset.from!,
        to: el.dataset.to!,
        left: box.left,
        right: box.right,
        dashed: stroke.classList.contains("how-dash"),
        drawn: stroke.classList.contains("how-dash") ? 1 - hidden : drawn,
        tip: Number(getComputedStyle(el.querySelector(".how-tip")!).opacity),
        color: getComputedStyle(el).color,
      };
    });
    return { x, legs };
  }, index);

const tokens = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("span");
    document.body.append(probe);
    const resolve = (name: string) => {
      probe.style.color = `var(${name})`;
      return getComputedStyle(probe).color;
    };
    const out = { ok: resolve("--ok"), confirm: resolve("--confirm"), blocked: resolve("--blocked"), accent: resolve("--accent") };
    probe.remove();
    return out;
  });

const FORMS = [
  { width: 1440, height: 900 },
  { width: 1366, height: 641 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 390, height: 664 },
  { width: 360, height: 700 },
];

test.describe("How it works", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  for (const form of FORMS) {
    test(`pins under the header, shows one step at a time and fills the screen, at ${form.width} by ${form.height}`, async ({ page }) => {
      await page.setViewportSize(form);
      await page.goto("/");
      const how = page.locator("[data-how]");
      await expect(how).toHaveAttribute("data-motion", "");
      const places: string[] = [];
      for (const [index, step] of steps.entries()) {
        await howAt(page, index + 1, 0.5);
        const where = `${form.width}x${form.height} step ${index + 1}`;
        await expect(how, where).toHaveAttribute("data-step", String(index + 1));
        const header = await page.locator("header.header").evaluate((el) => el.getBoundingClientRect().bottom);
        const stage = (await page.locator(".how-stage").boundingBox())!;
        expect(Math.abs(stage.y - header), where).toBeLessThan(1);
        expect(stage.y + stage.height, where).toBeLessThanOrEqual(form.height + 1);
        expect(await shown(page, ".how-caption"), where).toEqual([flat(step.caption)]);
        expect(await shown(page, ".how-count > *"), where).toEqual([`${index + 1} / ${steps.length}`]);
        const bottom = await page.locator(".how-step").nth(index).locator(".how-life").first().evaluate((el) => el.getBoundingClientRect().bottom);
        expect(stage.y + stage.height - bottom, `${where} leaves no band under the diagram`).toBeLessThan(40);
        places.push(JSON.stringify(await page.locator(".how-step").nth(index).locator(".how-head, .how-life").evaluateAll((items) => items.map((el) => [Math.round(el.getBoundingClientRect().x), Math.round(el.getBoundingClientRect().y)]))));
      }
      expect(new Set(places).size, "the diagram stays in one place from step to step").toBe(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(form.width);
    });
  }

  test("uses the owner's three captions word for word", async ({ page }) => {
    await page.goto("/");
    const captions = await page.locator(".how-caption").allTextContents();
    expect(captions.map(flat)).toEqual([...CAPTIONS]);
  });

  test("draws each step's request to the lifeline the record says it reached, and the answer back to the agent", async ({ page }) => {
    await page.goto("/");
    const color = await tokens(page);
    for (const [index, step] of steps.entries()) {
      await howAt(page, index + 1, 0.97);
      const { x, legs } = await geometry(page, index);
      expect(Object.keys(x)).toEqual(["agent", "hub", "printer"]);
      expect(Math.abs(x.hub - x.agent - (x.printer - x.hub))).toBeLessThan(2);
      const where = `step ${index + 1}`;
      for (const [place, row] of step.rows.entries()) {
        const drawn = legs.filter((leg) => leg.row === place);
        if (row.kind === "request") {
          expect(drawn.map((leg) => `${leg.from} ${leg.to}`), where).toEqual(row.legs.map((leg) => `${leg.from} ${leg.to}`));
          for (const [n, leg] of drawn.entries()) {
            expect(Math.abs(leg.left - x[leg.from]), `${where} ${leg.from}`).toBeLessThan(2);
            expect(Math.abs(leg.right - x[leg.to]), `${where} ${leg.to}`).toBeLessThan(2);
            expect(leg.dashed, where).toBe(false);
            expect(leg.drawn, where).toBeGreaterThan(0.98);
            expect(leg.tip, where).toBeGreaterThan(0.9);
            expect(leg.color, where).toBe(row.legs[n].held ? color.confirm : color.accent);
          }
        } else {
          const [reply] = drawn;
          const answer = row as Reply;
          expect(Math.abs(reply.left - x.agent), where).toBeLessThan(2);
          expect(Math.abs(reply.right - x[answer.from]), where).toBeLessThan(2);
          expect(reply.dashed, where).toBe(true);
          expect(reply.drawn, where).toBeGreaterThan(0.98);
          expect(reply.color, where).toBe(color[answer.tone]);
        }
      }
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-answer > span`), where).toEqual(step.rows.flatMap((row) => (row.kind === "reply" ? [row.answer] : [])));
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-rule > span`), where).toEqual([flat(step.rule.text)]);
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-printer dd > span`), where).toEqual(step.readings.map((reading) => flat(reading.becomes?.value ?? reading.value)));
    }
    expect(await shown(page, ".how-step:nth-child(3) .how-label > span")).toEqual(["cancel", "Approve"]);
  });

  test("starts each step with nothing drawn, and plays back the same way it plays forward", async ({ page }) => {
    await page.goto("/");
    const forward: string[] = [];
    for (const [index, step] of steps.entries()) {
      await howAt(page, index + 1, 0.04);
      const { legs } = await geometry(page, index);
      for (const leg of legs) expect(leg.drawn, `step ${index + 1}`).toBeLessThan(0.02);
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-answer > span`)).toEqual([]);
      const before = step.readings.map((reading) => flat(reading.value));
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-printer dd > span`)).toEqual(before);
      await howAt(page, index + 1, 0.6);
      forward.push(JSON.stringify(await geometry(page, index)));
    }
    await howAt(page, 3, 1);
    const backward: string[] = [];
    for (const index of [2, 1, 0]) {
      await howAt(page, index + 1, 0.6);
      backward.unshift(JSON.stringify(await geometry(page, index)));
    }
    expect(backward).toEqual(forward);
  });

  test("keeps every caption at the top of one slot, so the diagram never moves", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      const found = new Set<string>();
      for (const index of steps.keys()) {
        await howAt(page, index + 1, 0.5);
        found.add(
          JSON.stringify(
            await page
              .locator(".how-step")
              .nth(index)
              .evaluate((step) => {
                const caption = step.querySelector(".how-caption")!.getBoundingClientRect();
                const figure = step.querySelector(".how-figure")!.getBoundingClientRect();
                const line = parseFloat(getComputedStyle(step.querySelector(".how-caption")!).lineHeight);
                return { top: Math.round(caption.top), slot: Math.round(caption.height), figure: Math.round(figure.top), fits: Math.round(step.querySelector(".how-caption")!.scrollHeight / line) <= Math.round(caption.height / line) };
              }),
          ),
        );
      }
      expect([...found].length, `${viewport.width}`).toBe(1);
      expect(JSON.parse([...found][0]).fits).toBe(true);
    }
  });

  test("lets a person skip it, and scrolling past it never stops", async ({ page }) => {
    await page.goto("/");
    await howAt(page, 1, 0.5);
    await page.getByRole("link", { name: "Skip the three steps" }).click();
    await expect(page).toHaveURL(/#safe$/);
    await expect(page.locator("#safe-title")).toBeInViewport();
    await page.keyboard.press("Home");
    await page.waitForTimeout(300);
    await page.keyboard.press("End");
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => Math.abs(window.scrollY + innerHeight - document.documentElement.scrollHeight))).toBeLessThan(2);
    await howAt(page, 3, 1);
    const gap = await page.evaluate(() => document.querySelector(".how-onward")!.getBoundingClientRect().top - document.querySelector(".how-stage")!.getBoundingClientRect().bottom);
    expect(gap).toBeGreaterThanOrEqual(0);
    expect(gap).toBeLessThan(48);
  });

  test("ends with a link to the full example", async ({ page }) => {
    await page.goto("/");
    const link = page.getByRole("link", { name: "See the full example: an agent watching a 3D print overnight" });
    await expect(link).toHaveAttribute("href", "/docs/examples/3d-print-watch/");
    await link.click();
    await expect(page.locator("h1")).toHaveText("Example: an agent watching a 3D print");
  });

  test("changes no layout while it plays, once each step has shown", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    for (const step of [1, 2, 3, 1]) await howAt(page, step, 0.5);
    await howAt(page, 1, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    for (let at = 0; at <= 3; at += 0.25) await howAt(page, Math.floor(at) + 1, at - Math.floor(at));
    expect(await layouts()).toBe(before);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`draws no box, shadow or tinted area on the stage, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 664 }]) {
        await page.setViewportSize(viewport);
        await page.goto("/");
        await howAt(page, 3, 0.97);
        const boxes = await page.evaluate(() => {
          const out: string[] = [];
          const bg = getComputedStyle(document.body).backgroundColor;
          for (const el of document.querySelectorAll<HTMLElement>(".how-stage *")) {
            if (el.closest(".smooth") || !el.getClientRects().length) continue;
            const style = getComputedStyle(el);
            const box = el.getBoundingClientRect();
            const stroke = box.width <= 2.5 || box.height <= 2.5 || (box.width <= 8 && box.height <= 8);
            const name = `${el.tagName.toLowerCase()}.${String(el.getAttribute("class") ?? "").replace(/\s+/g, ".")}`;
            for (const side of ["top", "right", "bottom", "left"]) if (parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0) out.push(`${name} has a ${side} border`);
            if (style.boxShadow !== "none") out.push(`${name} has a shadow`);
            if (!stroke && style.backgroundColor !== "rgba(0, 0, 0, 0)" && style.backgroundColor !== bg) out.push(`${name} has a ${style.backgroundColor} background`);
          }
          return out;
        });
        expect(boxes, `${viewport.width}`).toEqual([]);
      }
    });
  }

  test("keeps every word on the stage at 13 px or more and inside a phone's screen", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }, { width: 390, height: 664 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      for (const index of steps.keys()) {
        await howAt(page, index + 1, 0.97);
        const found = await page.locator(".how-step").nth(index).evaluate((step, width) => {
          let least = Infinity;
          let outside = 0;
          const walker = document.createTreeWalker(step, NodeFilter.SHOW_TEXT);
          for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const parent = node.parentElement!;
            if (!node.textContent!.trim() || !parent.getClientRects().length) continue;
            least = Math.min(least, parseFloat(getComputedStyle(parent).fontSize));
            const range = document.createRange();
            range.selectNodeContents(node);
            const box = range.getBoundingClientRect();
            if (box.left < 0 || box.right > width) outside++;
          }
          return { least, outside };
        }, viewport.width);
        expect(found.least, `${viewport.width}`).toBeGreaterThanOrEqual(13);
        expect(found.outside, `${viewport.width} step ${index + 1}`).toBe(0);
      }
    }
  });

  test("with reduced motion shows the three steps as still panels, one under another, each drawn in full", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const how = page.locator("[data-how]");
    await expect(how).not.toHaveAttribute("data-motion");
    const panels = page.locator(".how-step");
    await expect(panels).toHaveCount(steps.length);
    const tops = await panels.evaluateAll((items) => items.map((el) => el.getBoundingClientRect().top));
    for (let index = 1; index < tops.length; index++) expect(tops[index]).toBeGreaterThan(tops[index - 1] + 200);
    for (const [index, step] of steps.entries()) {
      expect(flat((await panels.nth(index).locator(".how-caption").textContent())!)).toBe(step.caption);
      const { legs } = await geometry(page, index);
      for (const leg of legs) {
        expect(leg.drawn, `step ${index + 1}`).toBeGreaterThan(0.98);
        expect(leg.tip, `step ${index + 1}`).toBeGreaterThan(0.9);
      }
      expect(await shown(page, `.how-step:nth-child(${index + 1}) .how-printer dd > span`)).toEqual(step.readings.map((reading) => flat(reading.becomes?.value ?? reading.value)));
    }
    await expect(page.locator(".how-count")).toBeHidden();
    expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  });

  test("on a screen too short for the stage shows the still panels", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 560 });
    await page.goto("/");
    await expect(page.locator("[data-how]")).not.toHaveAttribute("data-motion");
    await expect(page.locator(".how-step").first()).toBeVisible();
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

  test("eases the wheel and leaves keyboard scrolling alone", async ({ page, browserName }) => {
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
