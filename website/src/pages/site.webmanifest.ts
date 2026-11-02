import type { APIRoute } from "astro";
import { PITCH, PRODUCT_NAME } from "../config/brand";
import { palette } from "../lib/palette.mjs";

export const GET: APIRoute = () =>
  new Response(
    JSON.stringify(
      {
        name: PRODUCT_NAME,
        short_name: PRODUCT_NAME,
        description: PITCH,
        start_url: "/",
        display: "browser",
        background_color: palette.light.bg,
        theme_color: palette.light.bg,
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      null,
      2,
    ),
    { headers: { "Content-Type": "application/manifest+json" } },
  );
