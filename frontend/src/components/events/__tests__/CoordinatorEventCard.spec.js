import { createApp, h, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it } from "vitest";

import CoordinatorEventCard from "@/components/events/CoordinatorEventCard.vue";

const CARD = {
  id: "e1",
  name: "Year-End Dinner",
  status: "planning",
  startsAt: "2026-11-13T02:00:00Z",
  flags: [],
  actionKind: null,
  outstanding: [],
};

const mounted = [];

async function mount(props) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { render: () => null } },
      { path: "/coordinator/events/:id", name: "coordinator-event", component: { render: () => null } },
    ],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(CoordinatorEventCard, props) }).use(router);
  app.mount(el);
  mounted.push(app);
  await router.isReady();
  await nextTick();
  return { el, link: el.querySelector("[data-event-card]") };
}

describe("CoordinatorEventCard", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("links the whole card to the event's review page, labelled for screen readers", async () => {
    const { link } = await mount({ card: CARD });

    expect(link.getAttribute("href")).toBe("/coordinator/events/e1");
    expect(link.getAttribute("aria-label")).toBe("More details about Year-End Dinner");
    expect(link.textContent).toContain("More details →");
    expect(link.textContent).toContain("Planning · 13 Nov 2026, 10:00 am");
    expect(link.textContent).toContain("Year-End Dinner");
  });

  it("is red with its action badge and flags when the event needs the coordinator", async () => {
    const { link } = await mount({
      card: { ...CARD, actionKind: "needs_alternative_venue", flags: ["venue_affected"], outstanding: ["Venue"] },
    });

    expect(link.dataset.tone).toBe("attention");
    expect(link.className).toContain("border-bauhaus-red");
    expect(link.querySelector("[data-action-badge]").textContent).toContain("Needs alternative venue");
    expect(link.textContent).toContain("Venue affected");
    expect([...link.querySelectorAll("[data-outstanding]")].map((chip) => chip.textContent.trim())).toEqual(["Venue"]);
  });

  it("says all arrangements are in place when nothing is outstanding", async () => {
    const { link } = await mount({ card: { ...CARD, status: "confirmed" } });

    expect(link.dataset.tone).toBe("done");
    expect(link.textContent).toContain("All arrangements in place");
    expect(link.querySelector("[data-outstanding]")).toBeNull();
  });

  it("shows a rejected request as closed: grey, with no footer", async () => {
    const { link } = await mount({ card: { ...CARD, status: "rejected" } });

    expect(link.dataset.tone).toBe("rejected");
    expect(link.className).toContain("bg-muted");
    expect(link.textContent).toContain("Rejected · 13 Nov 2026, 10:00 am");
    expect(link.querySelector("[data-card-footer]")).toBeNull();
    expect(link.textContent).not.toContain("More details");
    expect(link.textContent).not.toContain("All arrangements in place");
  });

  it("shows a past event as confirmed, without an action badge", async () => {
    const { link } = await mount({ card: { ...CARD, status: "confirmed", actionKind: "needs_alternative_venue" }, past: true });

    expect(link.dataset.tone).toBe("done");
    expect(link.querySelector("[data-action-badge]")).toBeNull();
  });
});
