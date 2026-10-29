export {};

declare module "astro" {
  interface AstroClientDirectives {
    "client:interact"?: boolean;
    "client:intent"?: boolean | string;
  }
}
