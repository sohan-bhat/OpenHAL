import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";
import type { Loader } from "astro/loaders";
import { i18nLoader } from "@astrojs/starlight/loaders";
import { docsSchema, i18nSchema } from "@astrojs/starlight/schema";
import { DOC_PATTERNS, SPEC_PATTERN } from "./lib/markdown/routes.mjs";
import { readVersions } from "./lib/spec-meta.mjs";

function whenPresent(present: () => boolean, inner: Loader): Loader {
  return {
    name: `optional-${inner.name}`,
    load: async (context) => {
      if (!present()) {
        context.store.clear();
        return;
      }
      await inner.load(context);
    },
  };
}

/**
 * Every page renders through <StarlightPage> from the repository's files and data, so Starlight's
 * own collection holds one draft, which a production build leaves out, and is never empty.
 */
const draft: Loader = {
  name: "openhal-starlight-draft",
  load: async ({ store, parseData }) => {
    store.clear();
    const id = "starlight-draft";
    store.set({ id, data: await parseData({ id, data: { title: "Draft", draft: true } }) });
  },
};

const docs = defineCollection({
  loader: draft,
  schema: docsSchema({ extend: z.object({ number: z.string().optional(), mono: z.boolean().default(true) }) }),
});

const i18n = defineCollection({ loader: i18nLoader(), schema: i18nSchema() });

const repo = defineCollection({
  loader: glob({ base: "..", pattern: DOC_PATTERNS, generateId: ({ entry }) => entry }),
  schema: z.object({ title: z.string().optional() }).passthrough(),
});

const spec = defineCollection({
  loader: whenPresent(
    () => readVersions().versions.length > 0,
    glob({ base: "..", pattern: SPEC_PATTERN, generateId: ({ entry }) => entry }),
  ),
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

const snippets = defineCollection({
  loader: glob({ base: "./src/content/snippets", pattern: "**/*.md" }),
  schema: z.object({ title: z.string() }),
});

export const collections = { docs, i18n, repo, spec, blog, snippets };
