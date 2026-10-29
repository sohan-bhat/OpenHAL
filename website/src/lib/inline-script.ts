import { minify, transformWithOxc } from "vite";

/**
 * A script minified for an inline <script>. TypeScript loses its types, and with `iife` the code
 * runs in a scope of its own with its exports dropped, so its names stay out of the page's globals.
 */
export async function inlineScript(source: string, filename: string, { iife = false } = {}): Promise<string> {
  const plain = filename.endsWith(".ts") ? (await transformWithOxc(source, filename, { lang: "ts" })).code : source;
  const body = iife ? `(() => {\n${plain.replace(/^export\s+/gm, "")}\n})();` : plain;
  const { code } = await minify(filename.replace(/\.ts$/, ".js"), body, { compress: true, mangle: true });
  return code.trim();
}
