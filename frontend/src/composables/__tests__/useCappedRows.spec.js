import { describe, expect, it } from "vitest";

import { CAPPED_ROWS_ROOM, capListRows } from "@/composables/useCappedRows";

// jsdom has no layout, so each item reports where it would sit: `perRow`
// items side by side, rows 100px apart, each item 90px tall.
function fakeList(count, perRow) {
  const list = { style: {}, getBoundingClientRect: () => ({ top: 0 }) };
  list.children = Array.from({ length: count }, (_, i) => {
    const top = Math.floor(i / perRow) * 100;
    return { getBoundingClientRect: () => ({ top, bottom: top + 90 }) };
  });
  return list;
}

describe("capListRows", () => {
  it("stops a grid at the bottom of its fourth row", () => {
    const list = fakeList(14, 3); // five rows of three, the last part-filled
    capListRows(list, 4);
    expect(list.style.maxHeight).toBe(`${390 + CAPPED_ROWS_ROOM}px`);
  });

  it("counts a single column one card per row", () => {
    const list = fakeList(6, 1);
    capListRows(list, 4);
    expect(list.style.maxHeight).toBe(`${390 + CAPPED_ROWS_ROOM}px`);
  });

  it("leaves a list of four rows or fewer uncapped, and clears an old cap", () => {
    const list = fakeList(12, 3);
    list.style.maxHeight = "100px";
    capListRows(list, 4);
    expect(list.style.maxHeight).toBe("");
  });

  it("uses the tallest card in the last visible row", () => {
    const list = fakeList(13, 3);
    list.children[10].getBoundingClientRect = () => ({ top: 300, bottom: 420 });
    capListRows(list, 4);
    expect(list.style.maxHeight).toBe(`${420 + CAPPED_ROWS_ROOM}px`);
  });
});
