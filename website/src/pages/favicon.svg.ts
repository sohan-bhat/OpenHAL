import type { APIRoute } from "astro";
import { faviconSvg } from "../lib/brand-mark";

export const GET: APIRoute = () => new Response(faviconSvg(), { headers: { "Content-Type": "image/svg+xml" } });
