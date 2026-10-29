import { defineRouteMiddleware } from "@astrojs/starlight/route-data";

/**
 * Leaves out the "On this page" outline on a page with fewer than two sections, where it would
 * list only Overview and maybe one heading, so the page's column takes the space instead.
 */
export const onRequest = defineRouteMiddleware((context) => {
  const route = context.locals.starlightRoute;
  const sections = route.toc?.items.filter((item) => item.slug !== "_top") ?? [];
  if (route.toc && sections.length < 2) route.toc = undefined;
});
