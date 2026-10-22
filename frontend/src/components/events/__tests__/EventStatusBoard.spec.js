import { createApp, h, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import EventStatusBoard from "@/components/events/EventStatusBoard.vue";

const mounted = [];

const COLUMNS = [
  { status: "under_review", label: "Under review", description: "Waiting.", needsAttention: false, events: [{ id: "a", name: "Alpha" }] },
  { status: "returned", label: "Returned", description: "Yours to fix.", needsAttention: true, events: [{ id: "b", name: "Beta" }] },
  { status: "planning", label: "Planning", description: "Arranging.", needsAttention: false, events: [] },
];

async function mountBoard(props = {}) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const onOpenStatus = vi.fn();
  const app = createApp({
    render: () =>
      h(EventStatusBoard, { columns: COLUMNS, itemKey: "id", onOpenStatus, ...props }, {
        card: ({ event, column }) => h("span", { "data-card": event.id }, `${event.name} in ${column.status}`),
      }),
  });
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return { el, onOpenStatus };
}

describe("EventStatusBoard", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("renders one column per status, in order, with its count and description", async () => {
    const { el } = await mountBoard();
    const columns = [...el.querySelectorAll("[data-status-group]")];
    expect(columns.map((node) => node.dataset.statusGroup)).toEqual(["under_review", "returned", "planning"]);
    expect(columns[0].querySelector("[data-column-header]").textContent).toContain("Under review");
    expect(columns[0].querySelector("[data-column-header]").textContent).toContain("1");
    expect(columns[0].querySelector("[data-column-header]").textContent).toContain("Waiting.");
  });

  it("turns a column header red only when the column needs attention", async () => {
    const { el } = await mountBoard();
    const header = (status) => el.querySelector(`[data-status-group="${status}"] [data-column-header]`);
    expect(header("returned").className).toContain("bg-bauhaus-red");
    expect(header("under_review").className).toContain("bg-muted");
    expect(header("under_review").className).not.toContain("bg-bauhaus-red");
  });

  it("renders each event through the card slot and says None. for an empty column", async () => {
    const { el } = await mountBoard();
    expect(el.querySelector('[data-card="a"]').textContent).toBe("Alpha in under_review");
    expect(el.querySelector('[data-card="b"]').textContent).toBe("Beta in returned");
    expect(el.querySelector('[data-status-group="planning"]').textContent).toContain("None.");
  });

  it("shows the colour legend", async () => {
    const { el } = await mountBoard();
    const legend = el.querySelector("[data-board-legend]");
    expect(legend.textContent).toContain("Red: needs your action");
    expect(legend.textContent).toContain("Blue: you can edit");
    expect(legend.textContent).toContain("Grey: waiting on others");
    expect(legend.textContent).toContain("Green: confirmed");
  });

  it("emits open-status with the column's status when its heading is pressed", async () => {
    const { el, onOpenStatus } = await mountBoard();
    el.querySelector('[aria-label="View all Returned events"]').click();
    expect(onOpenStatus).toHaveBeenCalledWith("returned");
  });
});
