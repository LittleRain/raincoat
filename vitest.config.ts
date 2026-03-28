import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@raincoat/shared-types": path.resolve(__dirname, "packages/shared-types/src"),
      "@raincoat/shared-config": path.resolve(__dirname, "packages/shared-config/src"),
      "@raincoat/task-sdk": path.resolve(__dirname, "packages/task-sdk/src"),
      "@raincoat/ui": path.resolve(__dirname, "packages/ui/src")
    }
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"]
  }
});
