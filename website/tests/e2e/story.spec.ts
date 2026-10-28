import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { SCENARIO_PATH, scenarioFrom } from "../../src/lib/scenario-data.mjs";
import { IDS, nb, storyFacts, storyLines, type Lifeline, type Sending } from "../../src/lib/story/facts";
import { COUNTED, PLACED, TOTAL, step, type StepId } from "../../src/lib/story/script";
import { storySequence } from "../../src/lib/story/timeline";

const scenarioFile = process.env.OPENHAL_SCENARIO ?? fileURLToPath(new URL(`../../../${SCENARIO_PATH}`, import.meta.url));
const scenario = scenarioFrom(readFileSync(scenarioFile, "utf8")) as any;
const facts = storyFacts(scenario);
const lines = storyLines(facts);
const sequence = storySequence(facts);
const nozzle = scenario.record.exchanges.find((exchange: any) => exchange.id === IDS.nozzle);
const flat = (text: string) => text.replace(/\s+/g, " ").trim();
const rows = sequence.rows;
const row = (id: Sending) => rows.find((item) => item.id === id)!;

async function storyTime(page: Page, t: number): Promise<void> {
  await page.evaluate(
    ([time, total]) => {
      const story = document.querySelector<HTMLElement>("[data-story]")!;
      const stage = story.querySelector<HTMLElement>(".story-stage")!;
      const runway = story.querySelector<HTMLElement>(".story-runway")!;
      let y = 0;
      for (let el: HTMLElement | null = story; el; el = el.offsetParent as HTMLElement | null) y += el.offsetTop;
      const top = parseFloat(getComputedStyle(stage).top) || 0;
      window.scrollTo({ top: y - top + (time * runway.offsetHeight) / total, behavior: "instant" });
    },
    [t, TOTAL] as const,
  );
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== "running"), undefined, { polling: 25 });
}

const shown = (page: Page, selector: string) =>
  page.evaluate(
    (query) => [...document.querySelectorAll<HTMLElement>(query)].filter((el) => Number(getComputedStyle(el).opacity) > 0.9 && el.getClientRects().length > 0).map((el) => el.textContent!.replace(/\s+/g, " ").trim()),
    selector,
  );

/** The middle of each lifeline, left to right, in px from the left of the page. */
const lifelines = (page: Page) =>
  page.evaluate(() =>
    Object.fromEntries([...document.querySelectorAll<HTMLElement>(".story-scene .lifeline")].map((el) => [el.dataset.line!, el.getBoundingClientRect().left + el.getBoundingClientRect().width / 2])),
  ) as Promise<Record<Lifeline, number>>;

/** Where each drawn leg of a row starts and where its arrowhead's tip is, counting only what shows. */
const legsOf = (page: Page, id: Sending) =>
  page.evaluate((name) => {
    const seen = (el: Element) => {
      for (let node: Element | null = el; node && !node.classList.contains("story-scene"); node = node.parentElement) if (Number(getComputedStyle(node).opacity) < 0.9) return false;
      return true;
    };
    return [...document.querySelectorAll<HTMLElement>(`.story-scene .leg[data-row="${name}"]`)].map((leg) => {
      const line = leg.querySelector<HTMLElement>(".stroke .line")!.getBoundingClientRect();
      const head = leg.querySelector<HTMLElement>(".stroke .head")!;
      return { start: line.left, end: line.right, tip: head.getBoundingClientRect().right, head: seen(head), color: getComputedStyle(leg.querySelector(".stroke")!).color };
    });
  }, id);

const tokens = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("span");
    document.body.append(probe);
    const resolve = (name: string) => {
      probe.style.color = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return getComputedStyle(probe).color;
    };
    const out = { ok: resolve("--ok"), confirm: resolve("--confirm"), blocked: resolve("--blocked"), accent: resolve("--accent"), quiet: resolve("--text-2"), bg: resolve("--bg") };
    probe.remove();
    return out;
  });

const FORMS = [
  { width: 1440, height: 900 },
  { width: 1366, height: 641 },
  { width: 1100, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 664 },
  { width: 390, height: 844 },
  { width: 360, height: 700 },
];

test.describe("the landing story", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  for (const form of FORMS) {
    test(`pins the whole diagram right under the header, at one size, at ${form.width} by ${form.height}`, async ({ page }) => {
      await page.setViewportSize(form);
      await page.goto("/");
      const story = page.locator("[data-story]");
      await expect(story).toHaveAttribute("data-camera", "");
      await expect(story).toHaveAttribute("data-ready", "");
      const places: string[] = [];
      for (const item of COUNTED) {
        await storyTime(page, item.from + item.length / 2);
        const box = await page.locator(".story-stage").boundingBox();
        const header = await page.locator(".site-header").evaluate((el) => el.getBoundingClientRect().height);
        const where = `${form.width}x${form.height} ${item.id}`;
        expect(Math.abs(box!.y - header), where).toBeLessThan(1);
        expect(box!.y + box!.height, where).toBeLessThanOrEqual(form.height + 1);
        const band = await page.locator(".story-count").evaluate((el) => el.getBoundingClientRect().top - document.querySelector(".site-header")!.getBoundingClientRect().bottom);
        expect(band, where).toBeLessThan(24);
        places.push(JSON.stringify(await page.locator(".story-scene :is(.lifeline, .seq-head, .cam-frame, .say, .leg)").evaluateAll((items) => items.map((el) => [el.getBoundingClientRect().x, el.getBoundingClientRect().y, el.getBoundingClientRect().width]))));
        expect(await page.locator(".story-scene").evaluate((el) => getComputedStyle(el).transform)).toBe("none");
      }
      expect(new Set(places).size).toBe(1);
    });
  }

  test("is the whole diagram and the list on a screen too short for the stage", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 629 });
    await page.goto("/");
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-camera");
    await expect(page.locator(".story-list > li")).toHaveCount(COUNTED.length);
    await expect(page.locator(".story-scene")).toBeVisible();
    expect(await shown(page, ".story-scene .answer")).toEqual(rows.flatMap((item) => item.words.filter((words) => words.answer).map((words) => words.answer!.text)));
  });

  test("opens with its title, how many steps follow and four empty lifelines", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, step("intro").from + step("intro").length / 2);
    expect(await shown(page, ".story-title")).toEqual([flat(lines.intro)]);
    expect(await shown(page, ".story-count > *")).toEqual([`${COUNTED.length} steps`]);
    expect(await shown(page, ".story-scene .seq-head")).toEqual(Object.values(sequence.heads));
    expect(await shown(page, ".story-scene .say > .label > *")).toEqual([]);
    expect(await shown(page, ".story-scene .answer")).toEqual([]);
    const drawn = await page.locator(".story-scene .leg .line").evaluateAll((items) => items.map((el) => el.getBoundingClientRect().width));
    expect(Math.max(...drawn)).toBeLessThan(1);
  });

  test("changes each caption with its arrow, and shows the answer once the arrow lands", async ({ page }) => {
    await page.goto("/");
    for (const [index, item] of COUNTED.entries()) {
      const id = item.id as Exclude<StepId, "intro">;
      const mine = rows.find((entry) => entry.id === id);
      for (const t of [item.from + 1, item.to - 1]) {
        await storyTime(page, t);
        const where = `${id} at ${t}`;
        expect(await shown(page, ".story-note"), where).toEqual([flat(nb(lines[id]))]);
        expect(await shown(page, ".story-count > *"), where).toEqual([`${index + 1} / ${COUNTED.length}`]);
        const answered = rows.flatMap((entry) => entry.words.filter((words) => words.answer && t >= words.answers).map((words) => words.answer!.text));
        expect(await shown(page, ".story-scene .answer"), where).toEqual(answered);
        if (mine) expect(await shown(page, `.story-scene .say[data-row="${id}"] .label .live`), where).toEqual(mine.words.filter((words) => t >= words.shows).map((words) => flat(nb(words.label))));
      }
      for (const [position, reading] of facts.printer.readings.entries()) {
        expect(await shown(page, `.story-scene .reading:nth-child(${position + 1}) .value > *`), `${id} ${reading.name}`).toEqual([flat(nb(reading.at[id]))]);
      }
    }
  });

  test("stops a refused request and the held cancel at the hub's lifeline, and takes the others to the printer's", async ({ page }) => {
    await page.goto("/");
    const x = await lifelines(page);
    for (const item of rows) {
      await storyTime(page, step(item.id).to - 1);
      const legs = await legsOf(page, item.id);
      expect(legs.length, item.id).toBe(item.legs.length);
      for (const [index, leg] of item.legs.entries()) {
        const where = `${item.id} leg ${index + 1}`;
        expect(Math.abs(legs[index].start - x[leg.from]), where).toBeLessThan(2);
        expect(Math.abs(legs[index].tip - x[leg.to]), where).toBeLessThan(2);
        expect(legs[index].head, where).toBe(true);
      }
      const last = item.legs[item.legs.length - 1].to;
      expect(last, item.id).toBe(item.id === "hot" || item.id === "cancel" ? "hub" : item.id === "ask" ? "agent" : "printer");
    }
    expect(row("approve").legs[0].from).toBe("owner");
  });

  test("draws the current arrow in the accent, holds the cancel in amber and settles every earlier arrow", async ({ page }) => {
    await page.goto("/");
    const color = await tokens(page);
    const strokes = (id: Sending) =>
      page.evaluate(
        (name) =>
          [...document.querySelectorAll<HTMLElement>(`.story-scene .leg[data-row="${name}"] .stroke`)].map((el) => ({
            kind: el.classList.contains("live") ? "live" : el.classList.contains("held") ? "held" : "quiet",
            on: Number(getComputedStyle(el).opacity) > 0.9,
            color: getComputedStyle(el).color,
          })),
        id,
      );
    const showing = async (id: Sending) => (await strokes(id)).filter((stroke) => stroke.on && stroke.kind !== "quiet").map((stroke) => stroke.color);
    await storyTime(page, step("pause").to - 1);
    expect(await showing("pause")).toEqual(row("pause").legs.map(() => color.accent));
    for (const id of ["ask", "look", "warm", "hot", "loose"] as Sending[]) expect(await showing(id), id).toEqual([]);
    await storyTime(page, step("cancel").to - 1);
    expect(await showing("cancel")).toEqual([color.confirm]);
    await storyTime(page, row("approve").legs[0].lands - 1);
    expect(await showing("cancel")).toEqual([color.confirm]);
    await storyTime(page, row("approve").legs[0].lands + 1);
    expect(await showing("cancel")).toEqual([]);
    expect(await showing("approve")).toEqual([color.accent]);
    await storyTime(page, step("approve").to - 1);
    expect(await showing("approve")).toEqual(row("approve").legs.map(() => color.accent));
    await storyTime(page, TOTAL - 1);
    for (const item of rows) expect(await showing(item.id), item.id).toEqual([]);
    for (const item of rows) for (const stroke of await strokes(item.id)) if (stroke.kind === "quiet") expect(stroke.color, item.id).toBe(color.quiet);
  });

  test("colors each answer by its outcome, as a word with nothing beside it", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, TOTAL - 1);
    const color = await tokens(page);
    const answers = await page.locator(".story-scene .answer").evaluateAll((items) => items.map((el) => ({ text: el.textContent!.trim(), color: getComputedStyle(el).color, children: el.children.length })));
    const expected = rows.flatMap((item) => item.words.filter((words) => words.answer).map((words) => ({ text: words.answer!.text, color: color[words.answer!.tone], children: 0 })));
    expect(answers).toEqual(expected);
    expect(answers.map((answer) => answer.text)).toContain(nozzle.error.data.name);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`draws no box, panel, frame or tinted area anywhere in the story, in the ${scheme} theme`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 664 }]) {
        await page.setViewportSize(viewport);
        await page.goto("/");
        await storyTime(page, TOTAL - 1);
        const boxes = await page.evaluate(() => {
          const out: string[] = [];
          const bg = getComputedStyle(document.body).backgroundColor;
          for (const el of document.querySelectorAll<HTMLElement | SVGElement>(".story-stage *")) {
            if (el.closest(".smooth") || !el.getClientRects().length) continue;
            const style = getComputedStyle(el);
            const box = el.getBoundingClientRect();
            const name = `${el.tagName.toLowerCase()}.${String(el.getAttribute("class") ?? "").replace(/\s+/g, ".")}`;
            const stroke = box.width <= 2.5 || box.height <= 2.5 || (box.width <= 8 && box.height <= 8);
            for (const side of ["top", "right", "bottom", "left"]) if (parseFloat(style.getPropertyValue(`border-${side}-width`)) > 0) out.push(`${name} has a ${side} border`);
            if (style.boxShadow !== "none") out.push(`${name} has a shadow`);
            if (!stroke && style.backgroundColor !== "rgba(0, 0, 0, 0)" && style.backgroundColor !== bg) out.push(`${name} has a ${style.backgroundColor} background`);
            if (el.tagName === "rect") out.push(`${name} is a rectangle`);
          }
          return out;
        });
        expect(boxes, `${viewport.width}`).toEqual([]);
      }
    });
  }

  test("keeps every label and answer between the lifelines of its arrow", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 390, height: 664 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await storyTime(page, TOTAL - 1);
      const x = await lifelines(page);
      const spills: string[] = [];
      for (const item of rows) {
        for (const [index, words] of item.words.entries()) {
          const rects = await page.locator(`.story-scene .say[data-row="${item.id}"]`).nth(index).evaluate((el) => {
            const out: Array<[number, number]> = [];
            for (const part of el.querySelectorAll(".quiet, .answer")) for (const rect of part.getClientRects()) out.push([rect.left, rect.right]);
            return out;
          });
          for (const [left, right] of rects) if (left < x[words.from] - 1 || right > x[words.to] + 1) spills.push(`${viewport.width} ${item.id} ${words.label}`);
        }
      }
      expect(spills).toEqual([]);
    }
  });

  test("shows the frame each read returned and marks what the agent noticed", async ({ page }) => {
    await page.goto("/");
    const frames = () => page.locator(".story-scene .cam-frame > svg").evaluateAll((items) => items.map((el) => Number(getComputedStyle(el).opacity) > 0.9));
    const seen = () => page.locator(".story-scene .cam-frame .seen").evaluateAll((items) => items.map((el) => Number(getComputedStyle(el).opacity) > 0.9));
    await storyTime(page, row("look").lands - 1);
    expect(await frames()).toEqual([true, false]);
    expect(await seen()).toEqual([false, false]);
    await storyTime(page, row("look").lands + 2);
    expect(await seen()).toEqual([true, false]);
    await storyTime(page, row("loose").lands - 1);
    expect(await frames()).toEqual([true, false]);
    expect(await seen()).toEqual([false, false]);
    await storyTime(page, row("loose").lands + 2);
    expect(await frames()).toEqual([false, true]);
    expect(await seen()).toEqual([false, true]);
    await storyTime(page, TOTAL - 1);
    expect(await frames()).toEqual([false, true]);
    await expect(page.locator(".story-scene .cam-note")).toHaveText("Webcam, demo frame");
  });

  for (const form of FORMS) {
    test(`keeps every caption at the top of one slot of fixed height at ${form.width} by ${form.height}`, async ({ page }) => {
      await page.setViewportSize(form);
      await page.goto("/");
      await expect(page.locator("[data-story]")).toHaveAttribute("data-ready", "");
      const heights = new Set<number>();
      for (const item of PLACED) {
        await storyTime(page, item.from + item.length / 2);
        const found = await page.evaluate(() => {
          const heads = document.querySelector<HTMLElement>(".story-heads")!;
          const caption = heads.querySelector<HTMLElement>("[data-on]")!.getBoundingClientRect();
          const box = heads.getBoundingClientRect();
          const line = parseFloat(getComputedStyle(heads).lineHeight);
          return { top: caption.top - box.top, height: Math.round(box.height), lines: Math.round(caption.height / line), slot: Math.round(box.height / line) };
        });
        const where = `${form.width}x${form.height} ${item.id}`;
        expect(Math.abs(found.top), where).toBeLessThan(1);
        expect(found.slot, where).toBe(form.width >= 1024 ? 2 : form.width >= 640 ? 3 : 4);
        expect(found.lines, where).toBeLessThanOrEqual(found.slot);
        heights.add(found.height);
      }
      expect(heights.size).toBe(1);
    });
  }

  test("changes no layout while it plays", async ({ page, browserName }) => {
    test.skip(browserName !== "chromium", "layout counters are a Chromium API");
    await page.goto("/");
    await storyTime(page, 0);
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");
    const layouts = async () => (await cdp.send("Performance.getMetrics")).metrics.find((metric) => metric.name === "LayoutCount")!.value;
    const before = await layouts();
    for (let t = 0; t <= TOTAL; t += 7) await storyTime(page, t);
    expect(await layouts()).toBe(before);
  });

  test("lets a person skip it and lands on what follows with no large gap", async ({ page }) => {
    await page.goto("/");
    await storyTime(page, step("warm").from + 10);
    await page.getByRole("link", { name: "Skip the demo" }).click();
    await expect(page).toHaveURL(/#safe$/);
    await expect(page.locator("#safe-title")).toBeInViewport();
    await storyTime(page, TOTAL + 1);
    const gap = await page.evaluate(() => document.querySelector("#safe-title")!.getBoundingClientRect().top - document.querySelector(".story-stage")!.getBoundingClientRect().bottom);
    expect(gap).toBeLessThan(120);
  });

  test("keeps every word on the stage at 13 px or more", async ({ page }) => {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 641 }, { width: 390, height: 844 }, { width: 390, height: 664 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await storyTime(page, TOTAL - 1);
      const smallest = await page.evaluate(() => {
        const walker = document.createTreeWalker(document.querySelector(".story-stage")!, NodeFilter.SHOW_TEXT);
        let least = Infinity;
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (node.textContent!.trim() && node.parentElement) least = Math.min(least, parseFloat(getComputedStyle(node.parentElement).fontSize));
        }
        return least;
      });
      expect(smallest).toBeGreaterThanOrEqual(13);
    }
  });

  test("with reduced motion it is the whole diagram, still, and a list of the same steps", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.locator("[data-story]")).not.toHaveAttribute("data-camera", "");
    await expect(page.locator(".story-list > li")).toHaveCount(COUNTED.length);
    for (const item of COUNTED) await expect(page.locator(".story-list")).toContainText(nb(lines[item.id as Exclude<StepId, "intro">]));
    await expect(page.locator(".story-list")).toContainText(nozzle.error.data.name);
    await expect(page.locator(".story-list")).toContainText(nb(facts.nozzle.refusal.reason));
    const x = await lifelines(page);
    for (const item of rows) {
      const legs = await legsOf(page, item.id);
      for (const [index, leg] of item.legs.entries()) expect(Math.abs(legs[index].tip - x[leg.to]), item.id).toBeLessThan(2);
    }
    expect(await shown(page, ".story-scene .answer")).toEqual(rows.flatMap((item) => item.words.filter((words) => words.answer).map((words) => words.answer!.text)));
    expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  });

  test("fits a phone's screen and never scrolls sideways", async ({ page }) => {
    for (const viewport of [{ width: 390, height: 844 }, { width: 360, height: 700 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await expect(page.locator("[data-story]")).toHaveAttribute("data-camera", "");
      for (const item of PLACED) {
        await storyTime(page, item.from + item.length / 2);
        const box = await page.locator(".story-stage").boundingBox();
        expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height + 1);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
        const outside = await page.locator(".story-scene :is(.seq-head, .say, .cam)").evaluateAll((items, width) => items.filter((el) => el.getBoundingClientRect().left < 0 || el.getBoundingClientRect().right > width).length, viewport.width);
        expect(outside).toBe(0);
      }
    }
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

  test("eases the wheel and leaves keyboard and anchor scrolling alone", async ({ page, browserName }) => {
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
