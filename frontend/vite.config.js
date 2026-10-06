import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import { coverageConfigDefaults } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
  },
  test: {
    // The router and auth store use browser globals (history, localStorage).
    environment: "jsdom",
    // Applies only with --coverage (`npm run test:coverage`). The target and
    // every exclusion's reason are in docs/CI.md §4 item 2.
    coverage: {
      provider: "v8",
      include: ["src/**"],
      // main.js only mounts the app when a browser loads the page; every
      // Playwright run exercises it.
      exclude: [...coverageConfigDefaults.exclude, "src/main.js"],
      reporter: ["text-summary", ["text", { skipFull: true }], "json-summary", "html"],
      // The floor, not the target: the measured baseline, raised each sprint
      // until it reaches 100. A change that lowers coverage fails the run.
      thresholds: { lines: 94 },
    },
  },
});
