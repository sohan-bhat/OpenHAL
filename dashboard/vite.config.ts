import { svelte } from "@sveltejs/vite-plugin-svelte";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const hub = process.env.OPENHAL_HUB ?? "http://127.0.0.1:7420";
const repo = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  plugins: [svelte()],
  base: "/",
  build: {
    outDir: "../openhal/hub/static",
    emptyOutDir: true,
    assetsDir: "assets",
    target: "es2022",
    chunkSizeWarningLimit: 400,
    rolldownOptions: {
      checks: { pluginTimings: false },
    },
  },
  server: {
    port: 5180,
    strictPort: true,
    fs: { allow: [repo] },
    proxy: {
      "/v1": { target: hub, ws: true, changeOrigin: false },
      "/rpc": { target: hub, ws: true, changeOrigin: false },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
});
