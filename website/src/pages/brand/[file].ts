import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { APIRoute } from "astro";
import { REPO_ROOT } from "../../lib/spec-meta.mjs";

const FILES = ["mark-light.svg", "mark-dark.svg", "wordmark-light.svg", "wordmark-dark.svg"];

export function getStaticPaths() {
  return FILES.map((file) => ({ params: { file } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(readFileSync(join(REPO_ROOT, "docs", "assets", String(params.file)), "utf8"), { headers: { "Content-Type": "image/svg+xml" } });
