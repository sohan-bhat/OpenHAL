// @ts-check
import { unified } from "@astrojs/markdown-remark";
import sitemap from "@astrojs/sitemap";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";
import { fileURLToPath } from "node:url";
import { rehypeDiagrams } from "./src/lib/markdown/mermaid.mjs";
import { rehypeCodeBlocks, rehypeGlossaryLinks, rehypeHeadingLinks, rehypeSpecSections, rehypeTables, rehypeTypography, remarkRepoLinks, remarkTitle } from "./src/lib/markdown/plugins.mjs";
import { deviceSchemaValidator } from "./src/lib/schema-validator-plugin.mjs";
import { DATED_NAMES } from "./src/lib/spec-meta.mjs";

const SITE_URL = process.env.OPENHAL_SITE ?? "https://openhal.dev";
const MOVED = ["/og/", "/spec/latest/", ...Object.keys(DATED_NAMES).map((name) => `/spec/${name}/`)];

const interactDirective = {
  name: "openhal-interact-directive",
  hooks: {
    "astro:config:setup": ({ addClientDirective }) => {
      addClientDirective({ name: "interact", entrypoint: fileURLToPath(new URL("./src/directives/interact.mjs", import.meta.url)) });
    },
  },
};

export default defineConfig({
  site: SITE_URL,
  trailingSlash: "always",
  compressHTML: true,
  integrations: [svelte(), interactDirective, sitemap({ filter: (page) => !MOVED.some((part) => page.includes(part)) && !page.endsWith("/spec/") })],
  markdown: {
    syntaxHighlight: false,
    processor: unified({
      smartypants: false,
      remarkPlugins: [remarkTitle, remarkRepoLinks],
      rehypePlugins: [rehypeDiagrams, rehypeCodeBlocks, rehypeTables, rehypeHeadingLinks, rehypeSpecSections, rehypeTypography, rehypeGlossaryLinks],
    }),
  },
  build: { inlineStylesheets: "auto" },
  devToolbar: { enabled: false },
  vite: {
    plugins: [deviceSchemaValidator()],
    server: { fs: { allow: [".."] } },
  },
});
