import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import TechnicalEventView from "@/views/events/TechnicalEventView.vue";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  equipmentApi: {
    technicalView: vi.fn(),
    reserveLine: vi.fn(),
    markNotAvailable: vi.fn(),
    setLineNote: vi.fn(),
    setExitConfirmation: vi.fn(),
  },
}));

const LINE = {
  id: "l1", submission_id: "s1", event_id: "e1", equipment_id: "p1", equipment_name: "4K Projector",
  quantity: 3, technical_requirements: null, status: "pending", technical_notes: null, not_available_reason: null,
  requested_by: { id: "c1", full_name: "Marcus Lim" }, created_at: "2026-10-06T02:00:00Z",
};

function view(overrides = {}) {
  return {
    event: { id: "e1", name: "Year-End Dinner", status: "planning", starts_at: "2026-11-20T10:00:00Z", ends_at: "2026-11-20T13:00:00Z", coordinator_name: "Marcus Lim" },
    technical_status: "pending",
    exit_confirmation: null,
    lines: [LINE],
    history: [{ action: "reserved", line_label: "3 × 4K Projector", from_status: "pending", to_status: "reserved", detail: null, actor_name: "Tan Wei", created_at: "2026-10-19T03:00:00Z" }],
    ...overrides,
  };
}

const apps = [];
async function mountView() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "t1", role: "tech_support", full_name: "Tan Wei" };
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/dashboard/tech-support", name: "dashboard-tech-support", component: { template: "<div />" } },
    { path: "/tech-support/events/:id", name: "tech-support-event", component: TechnicalEventView },
  ] });
  await router.push("/tech-support/events/e1");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(TechnicalEventView);
  app.use(pinia);
  app.use(router);
  app.mount(el);
  apps.push(app);
  await vi.waitFor(() => expect(document.body.textContent).toContain("Year-End Dinner"));
  return router;
}

const button = (text) => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text);
const checkbox = () => document.querySelector('input[type="checkbox"]');

beforeEach(() => {
  vi.clearAllMocks();
  equipmentApi.technicalView.mockResolvedValue(view());
});

afterEach(() => {
  apps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
});

describe("TechnicalEventView (SCRUM-24)", () => {
  it("shows the event, its technical status, the lines and the history", async () => {
    await mountView();

    const text = document.body.textContent;
    expect(text).toContain("Marcus Lim");
    expect(text).toContain("Technical status");
    expect(text).toContain("Pending");
    expect(text).toContain("4K Projector");
    expect(text).toContain("Reserved · 3 × 4K Projector · Pending → Reserved");
    expect(text).toContain("Tan Wei");
  });

  it("reserving a line calls the API and reloads (AC1)", async () => {
    equipmentApi.reserveLine.mockResolvedValue({ line_id: "l1", status: "reserved", free_quantity: 2 });
    await mountView();

    button("Reserve").click();
    await vi.waitFor(() => expect(equipmentApi.technicalView).toHaveBeenCalledTimes(2));

    expect(equipmentApi.reserveLine).toHaveBeenCalledWith("l1", "access");
  });

  it("a refusal shows the free count beside the line (AC3)", async () => {
    equipmentApi.reserveLine.mockRejectedValue(new ApiError("Not enough available: 1 free for this event's time. The line stays Pending.", 409));
    await mountView();

    button("Reserve").click();

    await vi.waitFor(() => expect(document.body.textContent).toContain("1 free for this event's time"));
  });

  it("marking Not available and saving notes reach the API (AC9)", async () => {
    equipmentApi.markNotAvailable.mockResolvedValue({});
    equipmentApi.setLineNote.mockResolvedValue({});
    await mountView();

    button("Mark not available").click();
    await nextTick();
    const reason = document.querySelector("#line-l1-reason");
    reason.value = "Only 2 in stock";
    reason.dispatchEvent(new Event("input"));
    await nextTick();
    button("Confirm not available").click();
    await vi.waitFor(() => expect(equipmentApi.markNotAvailable).toHaveBeenCalledWith("l1", "Only 2 in stock", "access"));
    // Wait for the reload that follows the action, when the line is usable again.
    await vi.waitFor(() => expect(equipmentApi.technicalView).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(document.querySelector("#line-l1-notes").disabled).toBe(false));

    const notes = document.querySelector("#line-l1-notes");
    notes.value = "Ask the vendor";
    notes.dispatchEvent(new Event("input"));
    await nextTick();
    button("Save notes").click();
    await vi.waitFor(() => expect(equipmentApi.setLineNote).toHaveBeenCalledWith("l1", "Ask the vendor", "access"));
  });

  it("the exit tick sends true, and shows who ticked it (AC10)", async () => {
    equipmentApi.setExitConfirmation.mockResolvedValue(null);
    await mountView();
    expect(document.body.textContent).toContain("Not recorded");

    equipmentApi.technicalView.mockResolvedValue(view({
      technical_status: "ready", exit_confirmation: { confirmed_by_name: "Tan Wei", confirmed_at: "2026-10-19T03:00:00Z" },
    }));
    checkbox().checked = true;
    checkbox().dispatchEvent(new Event("change"));

    await vi.waitFor(() => expect(document.body.textContent).toContain("Confirmed by Tan Wei"));
    expect(equipmentApi.setExitConfirmation).toHaveBeenCalledWith("e1", true, "access");
    expect(checkbox().checked).toBe(true);
    expect(document.body.textContent).toContain("Ready");
  });

  it("a refused tick shows why", async () => {
    equipmentApi.setExitConfirmation.mockRejectedValue(new ApiError("This event has no equipment lines, so there is nothing to confirm.", 409));
    await mountView();

    checkbox().checked = true;
    checkbox().dispatchEvent(new Event("change"));

    await vi.waitFor(() => expect(document.body.textContent).toContain("nothing to confirm"));
  });

  it("an event without equipment has no tick and says Not required", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({ lines: [], history: [], technical_status: "not_required" }));
    await mountView();

    expect(checkbox()).toBeNull();
    expect(document.body.textContent).toContain("No equipment requested");
    expect(document.body.textContent).toContain("Nothing recorded yet.");
  });

  it("a closed event is read-only", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({
      event: { ...view().event, status: "rejected" }, lines: [{ ...LINE, status: "released" }],
    }));
    await mountView();

    expect(document.body.textContent).toContain("can no longer be changed");
    expect(button("Reserve")).toBeUndefined();
    expect(checkbox()).toBeNull();
  });

  it("a load failure is reported", async () => {
    equipmentApi.technicalView.mockRejectedValue(new ApiError("Event not found.", 404));
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore();
    auth.token = "access";
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: "/dashboard/tech-support", name: "dashboard-tech-support", component: { template: "<div />" } },
      { path: "/tech-support/events/:id", name: "tech-support-event", component: TechnicalEventView },
    ] });
    await router.push("/tech-support/events/e1");
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp(TechnicalEventView);
    app.use(pinia);
    app.use(router);
    app.mount(el);
    apps.push(app);

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]').textContent).toContain("Event not found."));
  });

  it("Back to dashboard returns to the tech support dashboard", async () => {
    const router = await mountView();

    button("Back to dashboard").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-tech-support"));
  });
});

describe("TechnicalEventView re-review (story 37)", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    apps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows technical support what the approved change changed", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({
      lines: [{ ...LINE, status: "re_review" }],
      re_review_changes: { event: [{ field: "expected_attendance", before: 80, after: 120 }], spaces: [] },
      history: [{ action: "sent_for_re_review", line_label: "3 × 4K Projector", from_status: "reserved",
        to_status: "re_review", detail: "Check the bigger room", actor_name: "Marcus Lim",
        created_at: "2026-10-25T03:00:00Z" }],
    }));
    await mountView();

    const panel = document.querySelector('[data-testid="technical-re-review"]');
    expect(panel.textContent).toContain("What changed");
    expect(panel.textContent).toContain("Expected attendance: 80 → 120");
    expect(document.body.textContent).toContain("Sent for re-review");
  });
});


describe("TechnicalEventView re-review after a coordinator's edit (D70)", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    apps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  const EDITED = {
    action: "edited", request_id: "l1", line_label: "4 × 4K Projector", from_status: "reserved",
    to_status: "re_review", detail: "Quantity: 3 → 4.", actor_name: "Marcus Lim", created_at: "2026-10-26T03:00:00Z",
  };

  it("says the coordinator changed the line, not that the event's time changed", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({ lines: [{ ...LINE, status: "re_review" }], history: [EDITED] }));
    await mountView();

    const card = document.querySelector("article");
    expect(card.textContent).toContain("The coordinator changed this line. Quantity: 3 → 4.");
    expect(card.textContent).not.toContain("time changed");
  });

  it("doesn't show an older change request as what changed", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({
      lines: [{ ...LINE, status: "re_review" }],
      re_review_changes: { event: [{ field: "expected_attendance", before: 80, after: 120 }], spaces: [] },
      history: [EDITED],
    }));
    await mountView();

    expect(document.querySelector('[data-testid="technical-re-review"]')).toBeNull();
  });

  it("still shows the change request for a line it sent", async () => {
    equipmentApi.technicalView.mockResolvedValue(view({
      lines: [{ ...LINE, status: "re_review" }, { ...LINE, id: "l2", status: "re_review" }],
      re_review_changes: { event: [{ field: "expected_attendance", before: 80, after: 120 }], spaces: [] },
      history: [EDITED, { ...EDITED, action: "sent_for_re_review", request_id: "l2", detail: null }],
    }));
    await mountView();

    expect(document.querySelector('[data-testid="technical-re-review"]')).not.toBeNull();
  });
});
