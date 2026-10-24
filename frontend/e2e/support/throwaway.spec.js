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

// A run deletes only its own throwaway rows, plus rows an earlier run left more than
// STALE_AFTER ago, so it can't delete a concurrent run's rows (another developer's,
// or backend/scripts/verify_live.py's, which uses the same names).
describe("run-scoped cleanup", () => {
  function deletesSent(cleanup) {
    execFileSync.mockClear();
    execFileSync.mockReturnValue('{"rows": []}');
    cleanup();
    return execFileSync.mock.calls.map((call) => call[1].at(-1)).filter((sql) => /^\s*delete/i.test(sql));
  }

  it.each([
    ["accounts", () => throwaway.deleteThrowawayAccounts()],
    ["blocks", () => throwaway.deleteThrowawayBlocks()],
    ["events and their equipment", () => throwaway.deleteThrowawayEvents()],
    ["venues", () => throwaway.deleteThrowawayVenues()],
    ["equipment lines on the planning fixture", () => throwaway.deleteLiveCheckLines("fixture-1")],
  ])("limits every %s delete to this run or long-left-over rows", (_label, cleanup) => {
    const sent = deletesSent(cleanup);

    expect(sent.length).toBeGreaterThan(0);
    for (const sql of sent) {
      expect(sql).toContain(throwaway.RUN_ID);
      expect(sql).toContain(`interval '${throwaway.STALE_AFTER}'`);
    }
  });

  it("waits longer than any run before treating another run's rows as left over", () => {
    expect(throwaway.STALE_AFTER).toMatch(/^\d+ hours$/);
    expect(Number.parseInt(throwaway.STALE_AFTER, 10)).toBeGreaterThanOrEqual(6);
  });

  it("notes this run's blocks and equipment lines with its id", () => {
    execFileSync.mockReturnValue('{"rows": [{"id": "x"}]}');
    throwaway.createThrowawayBlock("v1", "2031-01-01 10:00+08", "2031-01-01 12:00+08");
    expect(execFileSync.mock.calls.at(-1)[1].at(-1)).toContain(`'live-check ${throwaway.RUN_ID}'`);
    expect(throwaway.liveCheckLineNote("lectern HDMI")).toContain(throwaway.RUN_ID);
  });
});
