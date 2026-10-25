import type { APIRoute } from "astro";
import { markSvg } from "../lib/brand-mark";

export const GET: APIRoute = () => new Response(markSvg({ size: 32 }), { headers: { "Content-Type": "image/svg+xml" } });
