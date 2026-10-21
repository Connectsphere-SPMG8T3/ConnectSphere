import { describe, expect, it } from "vitest";

// ConnectSphere is used for long administrative sessions, so text is set for
// reading: sentence case, normal letter spacing, nothing below 12px, and no
// extra-black weight (frontend/AGENTS.md, "Type"). This guards every component
// and view against the old all-caps label style creeping back in.
const sources = import.meta.glob(["../../**/*.vue", "../../**/*.js", "!../../**/__tests__/**"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const FORBIDDEN = /(?<![\w-])(?:[\w-]+:)*(uppercase|tracking-(?:tighter|tight|wide|wider|widest)|text-\[(?:[0-9]|1[01])px\]|font-black|leading-\[0\.9\])(?![\w-])/g;

const files = Object.entries(sources).map(([path, source]) => [path.replace("../../", "src/"), source]);

describe("readable type", () => {
  it("finds the components and views to check", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it.each(files)("%s uses readable type classes", (_path, source) => {
    expect(source.match(FORBIDDEN) ?? []).toEqual([]);
  });
});
