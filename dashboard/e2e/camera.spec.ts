import { expect, test } from "@playwright/test";
import { AgentClient, hubState, showFrame, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

test("the camera's latest frame shows in the device view, and Read frame reads it again", async ({ page }) => {
  await showFrame("first-layer");
  await page.goto("/#/devices/printer-cam");
  await expect(page.getByRole("heading", { name: "Printer camera", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Latest frame/, level: 2 })).toBeVisible();
  const frame = page.getByRole("main").getByRole("img", { name: /^Latest frame from Printer camera, frame, read at \d\d:\d\d:\d\d$/ });
  await expect(frame).toBeVisible();
  expect(await frame.evaluate((image: HTMLImageElement) => [image.naturalWidth, image.naturalHeight])).toEqual([640, 480]);
  expect((await frame.boundingBox())!.width).toBeGreaterThanOrEqual(320);
  const caption = page.getByRole("main").locator("figcaption");
  await expect(caption).toContainText("image/jpeg");
  await expect(caption).toContainText("640 × 480");
  await expect(caption).toContainText("19409 bytes");
  await expect(page.getByRole("main").locator("a img")).toHaveCount(0);
  expect(await frame.getAttribute("src")).toMatch(/^data:image\/jpeg;base64,\/9j\//);
  await expect(page.locator("main tr").filter({ hasText: "frame" })).toContainText("image/jpeg 640 × 480");
  await expect(page.getByRole("main").locator("dl.facts")).toContainText("reads only");

  await showFrame("come-loose");
  await page.getByRole("button", { name: "Read frame" }).click();
  await expect(caption).toContainText("23567 bytes");
  await expect(page.locator("main tr").filter({ hasText: "frame" })).toContainText("image/jpeg 640 × 480");
});

test("the message log shows a frame read as its description, never its base64", async ({ page, browserName, context }) => {
  await showFrame("first-layer");
  await page.goto("/#/devices/printer");
  const agent = await AgentClient.connect("frame-agent", hubState().printToken);
  const read = await agent.call("hal/read", { device: "printer-cam", channel: "frame" });
  agent.close();
  expect(String((read.result?.value as { data?: string }).data).startsWith("/9j/")).toBe(true);

  const log = page.getByRole("region", { name: "Messages" });
  const result = log.locator('li[data-kind="result"]').filter({ hasText: "frame-agent" }).filter({ hasText: "printer-cam" }).last();
  await expect(result).toContainText('"mimeType": "image/jpeg", "bytes": 19409, "width": 640, "height": 480');
  await expect(result).not.toContainText("/9j/");
  await result.getByRole("button", { name: "Show the whole message" }).click();
  await expect(result).toContainText('"data": <base64 not shown>');
  expect(await log.textContent()).not.toContain("/9j/");
  await expect(result.locator("img, a")).toHaveCount(0);

  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy as text" }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toContain('"data": <base64 not shown>');
    expect(copied).not.toContain("/9j/");
  }
});
