import type { APIRoute, GetStaticPaths } from "astro";
import { ICON_SIZES, iconPng } from "../lib/icons";

export const getStaticPaths: GetStaticPaths = () => Object.entries(ICON_SIZES).map(([icon, size]) => ({ params: { icon }, props: { size } }));

export const GET: APIRoute = async ({ props }) =>
  new Response(await iconPng((props as { size: number }).size), { headers: { "Content-Type": "image/png" } });
