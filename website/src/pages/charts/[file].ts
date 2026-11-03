import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { APIRoute } from "astro";
import { CHART_FILES } from "../../lib/story/how";
import { REPO_ROOT } from "../../lib/spec-meta.mjs";

export function getStaticPaths() {
  return CHART_FILES.map((file) => ({ params: { file } }));
}

export const GET: APIRoute = ({ params }) => new Response(readFileSync(join(REPO_ROOT, "docs", "assets", String(params.file))), { headers: { "Content-Type": "image/png" } });
