import { defineConfig, devices } from "@playwright/test";

// End-to-end specs run against the real app: a running frontend, a running
// backend, and the live Supabase project behind it. Nothing is mocked, so
// start both servers first (docs/test-cases/runs/README.md).
//
// Spec files end in .e2e.js so Vitest's default *.spec.js / *.test.js
// pattern never picks them up.
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.js",
  globalSetup: "./e2e/support/global-setup.js",
  // The specs share the seeded accounts, and every sign-in counts towards
  // Supabase's per-IP rate limit, so run one at a time.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
