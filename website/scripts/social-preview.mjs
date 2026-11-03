/**
 * Render the repository's social preview into docs/assets/social-preview.png.
 *
 *     pnpm --dir website exec node scripts/social-preview.mjs
 *
 * Vite loads src/lib/social-preview.ts the way the site build loads the OG images, so the preview
 * uses the same palette, fonts, wordmark and renderer. No server port opens. The PNG goes up by hand
 * in the repository's settings, under Social preview.
 */
import { writeFileSync } from "node:fs";
import { relative } from "node:path";
import { createServer } from "vite";

const server = await createServer({
  configFile: false,
  logLevel: "error",
  appType: "custom",
  server: { middlewareMode: true, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true, include: [] },
});
try {
  const { SOCIAL_PREVIEW_FILE, socialPreviewImage } = await server.ssrLoadModule("/src/lib/social-preview.ts");
  const png = await socialPreviewImage();
  writeFileSync(SOCIAL_PREVIEW_FILE, png);
  console.log(`wrote ${relative(process.cwd(), SOCIAL_PREVIEW_FILE)} (${Math.round(png.length / 1024)} KB)`);
} finally {
  await server.close();
}
