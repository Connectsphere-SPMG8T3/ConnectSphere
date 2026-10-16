// Mutation testing (docs/MUTATION_TESTING.md). Run one area at a time, e.g.
//   npm run test:mutation -- --mutate "src/stores/**/*.js,!src/**/__tests__/**"
// (a --mutate flag replaces the list below, so repeat the test-file exclusion).
// Not a CI gate: survivors are triaged by hand, so no break threshold.
/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
export default {
  testRunner: "vitest",
  // .vue files are left out: Stryker's instrumentation breaks `defineProps()` in
  // <script setup> (the Vue compiler refuses the helper variables it adds).
  mutate: ["src/**/*.js", "!src/**/__tests__/**", "!src/main.js"],
  coverageAnalysis: "perTest",
  reporters: ["clear-text", "progress", "html"],
  htmlReporter: { fileName: "reports/mutation/index.html" },
  thresholds: { high: 90, low: 75, break: null },
};
