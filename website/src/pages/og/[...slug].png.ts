import type { APIRoute, GetStaticPaths } from "astro";
import { ogImage } from "../../lib/og";
import { allPages, ogSlug, type PageInfo } from "../../lib/pages";

export const getStaticPaths: GetStaticPaths = async () =>
  (await allPages()).map((page) => ({ params: { slug: ogSlug(page.path) }, props: page }));

export const GET: APIRoute = async ({ props }) => {
  const page = props as PageInfo;
  return new Response(await ogImage(page.title, page.kind), { headers: { "Content-Type": "image/png" } });
};
