// @ts-check
import { unified } from "@astrojs/markdown-remark";
import sitemap from "@astrojs/sitemap";
import svelte from "@astrojs/svelte";
import { defineConfig } from "astro/config";
import rehypeMermaid from "rehype-mermaid";
import { rehypeCodeBlocks, rehypeTables, remarkRepoLinks, remarkTitle } from "./src/lib/markdown/plugins.mjs";
import { mermaidConfig, mermaidDarkConfig } from "./src/lib/markdown/mermaid.mjs";
import { deviceSchemaValidator } from "./src/lib/schema-validator-plugin.mjs";

// The site's address. The domain is not bought yet (NEEDS_HUMAN.md item 2), so this is a
// placeholder. Change it here and nowhere else.
const SITE_URL = "https://openhal.dev";

export default defineConfig({
  site: SITE_URL,
  trailingSlash: "always",
  integrations: [svelte(), sitemap({ filter: (page) => !page.includes("/og/") })],
  markdown: {
    syntaxHighlight: false,
    processor: unified({
      smartypants: false,
      remarkPlugins: [remarkTitle, remarkRepoLinks],
      rehypePlugins: [
        [rehypeMermaid, { strategy: "img-svg", dark: mermaidDarkConfig, mermaidConfig }],
        rehypeCodeBlocks,
        rehypeTables,
      ],
    }),
  },
  build: { inlineStylesheets: "auto" },
  devToolbar: { enabled: false },
  vite: {
    plugins: [deviceSchemaValidator()],
    server: { fs: { allow: [".."] } },
  },
});
