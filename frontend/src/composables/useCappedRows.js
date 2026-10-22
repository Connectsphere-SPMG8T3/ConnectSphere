import { onBeforeUnmount, onMounted, watch } from "vue";

// Room below the last visible row for a card's hover lift.
export const CAPPED_ROWS_ROOM = 8;

/**
 * Caps a list (a grid or a single column) at `maxRows` rows of items, so the
 * rest scroll inside it. Items vary in height, so the cap is measured from the
 * bottom of the tallest item in the last visible row rather than set as a
 * fixed height. Items sharing a top edge count as one row.
 */
export function capListRows(list, maxRows, room = CAPPED_ROWS_ROOM) {
  const rowBottoms = [];
  let rowTop = null;
  for (const item of list.children) {
    const { top, bottom } = item.getBoundingClientRect();
    if (rowTop === null || Math.abs(top - rowTop) >= 1) {
      rowBottoms.push(bottom);
      rowTop = top;
    } else {
      rowBottoms[rowBottoms.length - 1] = Math.max(rowBottoms[rowBottoms.length - 1], bottom);
    }
  }
  list.style.maxHeight =
    rowBottoms.length > maxRows
      ? `${rowBottoms[maxRows - 1] - list.getBoundingClientRect().top + room}px`
      : "";
}

/**
 * Keeps the lists `getLists()` returns capped at `maxRows` rows, re-measuring
 * after `sources` change and when the window resizes. The lists also need
 * `overflow-y-auto`.
 */
export function useCappedRows(getLists, sources, maxRows = 4) {
  const cap = () => getLists().forEach((list) => list && capListRows(list, maxRows));
  watch(sources, cap, { flush: "post", immediate: true });
  onMounted(() => window.addEventListener("resize", cap));
  onBeforeUnmount(() => window.removeEventListener("resize", cap));
  return cap;
}
