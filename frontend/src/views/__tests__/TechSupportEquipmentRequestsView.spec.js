import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import TechSupportEquipmentRequestsView from "@/views/equipment/TechSupportEquipmentRequestsView.vue";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: { requestList: vi.fn() },
}));

function line(overrides) {
  return {
    id: "l1", submission_id: "s1", event_id: "event-1", equipment_id: "p1", equipment_name: "4K Projector",
    equipment_type: "AV", quantity: 2, technical_requirements: null, status: "pending",
    technical_notes: null, not_available_reason: null,
    requested_by: { id: "m1", full_name: "Marcus Lim" }, created_at: "2026-10-06T02:00:00Z",
    event_name: "Year-End Dinner", event_starts_at: "2026-11-05T02:00:00Z",
    ...overrides,
  };
}

const LINES = [
  line({ id: "a", event_id: "e-a", event_name: "Summit", event_starts_at: "2026-11-20T02:00:00Z", technical_requirements: "HDMI to the lectern" }),
  line({ id: "b", event_id: "e-b", event_name: "Annual Dinner", status: "re_review", equipment_id: "m1", equipment_name: "Wireless Mic", equipment_type: "Audio", event_starts_at: "2026-11-01T02:00:00Z" }),
  line({ id: "c", event_id: "e-c", event_name: "Career Fair", status: "reserved" }),
  line({ id: "d", event_id: "e-d", event_name: "Breakfast", status: "rejected", not_available_reason: "Only 1 in stock" }),
];

const apps = [];
async function mountView() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "t1", role: "tech_support", full_name: "Daniel Wong" };
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/dashboard/tech-support", name: "dashboard-tech-support", component: { template: "<div />" } },
    { path: "/dashboard/tech-support/requests", name: "dashboard-tech-support-requests", component: TechSupportEquipmentRequestsView },
    { path: "/tech-support/events/:id", name: "tech-support-event", component: { template: "<div />" } },
  ] });
  await router.push("/dashboard/tech-support/requests");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(TechSupportEquipmentRequestsView).use(pinia).use(router);
  app.mount(el);
  apps.push(app);
  await vi.waitFor(() => expect(equipmentApi.requestList).toHaveBeenCalled());
  await vi.waitFor(() => expect(el.textContent).not.toContain("Loading requests"));
  return el;
}

const cards = (el) => [...el.querySelectorAll("[data-testid=equipment-request-card]")];
const select = (el, label) => [...el.querySelectorAll("label")].find((l) => l.textContent.includes(label))
  ?.closest("div")?.querySelector("select");

async function choose(el, label, value) {
  const control = select(el, label);
  control.value = value;
  control.dispatchEvent(new Event("change"));
  await nextTick();
}

beforeEach(() => {
  vi.clearAllMocks();
  equipmentApi.requestList.mockResolvedValue({ lines: LINES });
});

afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("TechSupportEquipmentRequestsView (SCRUM-24)", () => {
  // D75 (developer decision, 2026-11-06): the page opens on All statuses, so
  // these lines are reached by choosing "Waiting on you".
  it("Waiting on you lists the lines waiting on tech support, soonest event first", async () => {
    const el = await mountView();
    await choose(el, "Status", "waiting");

    expect(el.textContent).toContain("Equipment requests");
    expect(cards(el).map((c) => c.dataset.requestStatus)).toEqual(["re_review", "pending"]);
    const first = cards(el)[0].textContent;
    expect(first).toContain("Wireless Mic");
    expect(first).toContain("Audio · Re-review");
    expect(first).toContain("Annual Dinner");
    expect(first).toContain("Marcus Lim");
    expect(first).toMatch(/Waiting \d+ days/);
    expect(cards(el)[1].textContent).toContain("HDMI to the lectern");
  });

  it("each line opens its event's technical page", async () => {
    const el = await mountView();

    expect(cards(el)[0].querySelector("a").getAttribute("href")).toBe("/tech-support/events/e-b");
  });

  it("all statuses keep resolved lines for reference, with the reason", async () => {
    const el = await mountView();

    await choose(el, "Status", "all");

    expect(cards(el)).toHaveLength(4);
    const refused = cards(el).find((c) => c.dataset.requestStatus === "rejected");
    expect(refused.textContent).toContain("Not available: Only 1 in stock");
    expect(refused.textContent).not.toMatch(/Waiting \d+ days/);
  });

  it("filters by equipment and sorts by event name or type", async () => {
    const el = await mountView();
    await choose(el, "Status", "all");

    await choose(el, "Equipment", "m1");
    expect(cards(el).map((c) => c.dataset.requestStatus)).toEqual(["re_review"]);

    await choose(el, "Equipment", "all");
    await choose(el, "Sort by", "event_name");
    expect(cards(el).map((c) => c.textContent.match(/(Summit|Annual Dinner|Career Fair|Breakfast)/)[1]))
      .toEqual(["Annual Dinner", "Breakfast", "Career Fair", "Summit"]);
  });

  it("says when nothing matches", async () => {
    equipmentApi.requestList.mockResolvedValue({ lines: [line({ status: "reserved" })] });
    const el = await mountView();
    await choose(el, "Status", "waiting");

    expect(cards(el)).toHaveLength(0);
    expect(el.textContent).toContain("No matching requests");
  });

  it("shows the error rather than an empty list when the requests can't load", async () => {
    equipmentApi.requestList.mockRejectedValue(new Error("Service unavailable"));
    const el = await mountView();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable"));
    expect(el.textContent).toContain("Requests unavailable");
  });

  it("has a breadcrumb back to the dashboard that names the current page", async () => {
    const el = await mountView();

    const back = [...el.querySelectorAll('nav[aria-label="Breadcrumb"] a')].find((a) => a.textContent.trim() === "Dashboard");
    expect(back.getAttribute("href")).toBe("/dashboard/tech-support");
    expect(el.querySelector('[aria-current="page"]').textContent.trim()).toBe("Equipment requests");
  });
});
