// The e2e support code reads the Supabase CLI's JSON in either of its two shapes
// (the same bug as backend/scripts/verify_live.py, D28): `{"rows": [...]}` under an
// agent, a bare list in a plain terminal, and `[]` when a delete matched nothing.
import { describe, expect, it } from "vitest";

import { parseRows } from "./throwaway.js";

describe("parseRows", () => {
  it("reads the wrapped object form", () => {
    expect(parseRows('Initialising\n{"boundary":"b","rows":[{"x":1}],"warning":"w"}\n')).toEqual([{ x: 1 }]);
  });

  it("reads a bare list", () => {
    expect(parseRows('[\n  {"x": 1},\n  {"x": 2}\n]\n')).toEqual([{ x: 1 }, { x: 2 }]);
  });

  it("treats an empty result as no rows rather than throwing", () => {
    expect(parseRows("[]\n")).toEqual([]);
  });

  it("ignores notices after the JSON", () => {
    expect(parseRows('[{"x":1}]\nA new version of Supabase CLI is available: v9\n')).toEqual([{ x: 1 }]);
  });

  it("treats an object with no rows as none", () => {
    expect(parseRows('{"boundary":"b"}')).toEqual([]);
  });

  it("says so when the CLI printed no JSON", () => {
    expect(() => parseRows("Initialising login role...\n")).toThrow(/no JSON/);
  });
});
