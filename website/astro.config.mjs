// @ts-check
import { unified } from "@astrojs/markdown-remark";
import sitemap from "@astrojs/sitemap";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";
import { fileURLToPath } from "node:url";
import { rehypeDiagrams } from "./src/lib/markdown/mermaid.mjs";
import { rehypeCodeBlocks, rehypeHeadingLinks, rehypeTables, rehypeTypography, remarkRepoLinks, remarkTitle } from "./src/lib/markdown/plugins.mjs";
import { deviceSchemaValidator } from "./src/lib/schema-validator-plugin.mjs";

const SITE_URL = process.env.OPENHAL_SITE ?? "https://openhal.dev";

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
  integrations: [svelte(), interactDirective, sitemap({ filter: (page) => !page.includes("/og/") && !page.includes("/spec/latest/") && !page.endsWith("/spec/") })],
  markdown: {
    syntaxHighlight: false,
    processor: unified({
      smartypants: false,
      remarkPlugins: [remarkTitle, remarkRepoLinks],
      rehypePlugins: [rehypeDiagrams, rehypeCodeBlocks, rehypeTables, rehypeHeadingLinks, rehypeTypography],
    }),
  },
  build: { inlineStylesheets: "auto" },
  devToolbar: { enabled: false },
  vite: {
    plugins: [deviceSchemaValidator()],
    server: { fs: { allow: [".."] } },
  },
});
