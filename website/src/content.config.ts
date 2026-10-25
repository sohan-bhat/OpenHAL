import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";
import { DOC_PATTERNS } from "./lib/markdown/routes.mjs";

// The repository's own Markdown, read at build time so the site can't drift from it.
// Entry ids are repository paths, for example docs/SAFETY.md.
const docs = defineCollection({
  loader: glob({ base: "..", pattern: DOC_PATTERNS, generateId: ({ entry }) => entry }),
  schema: z.object({ title: z.string().optional() }).passthrough(),
});

const blog = defineCollection({
  loader: glob({ base: "./src/content/blog", pattern: "**/*.md" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.coerce.date(),
    author: z.string(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { docs, blog };
