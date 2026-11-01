export {};

declare module "astro" {
  interface AstroClientDirectives {
    "client:query"?: boolean | string;
  }
}
