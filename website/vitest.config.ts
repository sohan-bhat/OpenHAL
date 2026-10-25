import { defineConfig } from "vitest/config";
import { deviceSchemaValidator } from "./src/lib/schema-validator-plugin.mjs";

export default defineConfig({
  plugins: [deviceSchemaValidator()],
  test: {
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
  },
});
