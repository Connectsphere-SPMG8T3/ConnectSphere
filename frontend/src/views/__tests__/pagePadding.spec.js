import { describe, expect, it } from "vitest";

// Every page sits inside App.vue's gutters (pl-4 pr-6 sm:pl-8 sm:pr-10), so a
// page's <main> sets only vertical padding. Adding side padding or a max width
// on top makes the page narrower and more indented than the rest of the app
// (frontend/AGENTS.md, "Page padding").
const views = import.meta.glob("../**/*.vue", { query: "?raw", import: "default", eager: true });

const mains = Object.entries(views)
  .map(([path, source]) => [path.replace("../", "views/"), source.match(/<main\b[^>]*>/)?.[0]])
  .filter(([, main]) => main);

describe("page padding", () => {
  it("finds the pages to check", () => {
    expect(mains.length).toBeGreaterThan(10);
  });

  it.each(mains)("%s uses the shared page container", (_path, main) => {
    const classes = main.match(/class="([^"]*)"/)?.[1].split(/\s+/) ?? [];
    expect(classes).toContain("py-8");
    expect(classes.filter((name) => /^(?:[a-z]+:)?(?:px|pl|pr|mx|max-w)-/.test(name))).toEqual([]);
  });
});
