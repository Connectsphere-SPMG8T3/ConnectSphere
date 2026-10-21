// The e2e support code reads the Supabase CLI's JSON in either of its two shapes
// (the same bug as backend/scripts/verify_live.py, D28): `{"rows": [...]}` under an
// agent, a bare list in a plain terminal, and `[]` when a delete matched nothing.
import { describe, expect, it, vi } from "vitest";

import * as throwaway from "./throwaway.js";
import { execFileSync } from "node:child_process";
vi.mock("node:child_process", () => {
  const execFileSync = vi.fn();
  return {execFileSync, default: {execFileSync}};
});

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


it("flags only a disposable booking for the safety follow-up browser check", () => {
  execFileSync.mockReturnValue('{"rows": []}');
  expect(throwaway.setThrowawayBookingSafetyRejected).toBeTypeOf("function");
  throwaway.setThrowawayBookingSafetyRejected("b1");
  const sql = execFileSync.mock.calls.at(-1)[1].at(-1);
  expect(sql).toContain("flag = 'safety_rejected'");
  expect(sql).toContain("flag_reason = 'live check exits'");
  expect(sql).toContain("flagged_at = now()");
  expect(sql).toContain("id = 'b1'");
  expect(sql).toContain("name like 'live-check %'");
});
