import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn(), assign: vi.fn() },
}));

const QUEUE_ID = "e0000000-0000-4000-8000-000000000301";
const ASSIGNED_ID = "e0000000-0000-4000-8000-000000000302";

const PAYLOAD = {
  unassigned: [
    {
      event_id: QUEUE_ID, event_name: "Partner Summit", status: "submitted", starts_at: "2026-11-12T02:00:00Z", version: 3,
      organiser_name: "Olivia Tan", purpose: "Quarterly partner meeting", expected_attendance: 12,
      coordinator: null, assigned_at: null,
    },
  ],
  active_events: [
    {
      event_id: ASSIGNED_ID, event_name: "Year-End Dinner", status: "planning", starts_at: "2026-12-12T02:00:00Z", version: 8,
      organiser_name: "Olivia Tan", purpose: null, expected_attendance: null,
      coordinator: { id: "c1", full_name: "Marcus Lim" }, assigned_at: "2026-10-10T01:00:00Z",
    },
  ],
  coordinators: [
    { id: "c1", full_name: "Marcus Lim", active_count: 1 },
    { id: "c2", full_name: "Priya Nair", active_count: 0 },
  ],
};

const mountedApps = [];

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mountView(eventId, seed) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "l1", full_name: "Joyce Lim", role: "event_coordinator_lead" };
  auth.sessionVerified = true;

  if (seed) seed(await import("@/features/events/leadDashboardStore").then((m) => m.useLeadDashboardStore()));
  const { default: router } = await import("@/router");
  await router.push({ name: "lead-event", params: { id: eventId } });
  const { default: View } = await import("@/views/events/LeadEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await flush();
  return { el, router };
}

const picker = (el) => el.querySelector('select[aria-label="Choose a coordinator"]');
const reassignButton = (el) => el.querySelector('button[aria-label="Reassign event"]');

function choose(el, value) {
  const select = picker(el);
  select.value = value;
  select.dispatchEvent(new Event("change"));
}

describe("LeadEventView (CR-101 AC3)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    toastState.value = null;
    eventsApi.leadDashboard.mockResolvedValue(PAYLOAD);
  });

  it("loads the dashboard when opened directly and shows the event's details", async () => {
    const { el } = await mountView(QUEUE_ID);

    expect(eventsApi.leadDashboard).toHaveBeenCalledTimes(1);
    expect(el.textContent).toContain("Partner Summit");
    expect(el.textContent).toContain("Awaiting assignment");
    expect(el.textContent).toContain("Olivia Tan");
    expect(el.textContent).toContain("Quarterly partner meeting");
    expect(el.textContent).toContain("Unassigned");
  });

  it("always reloads, and never shows rows left in the store by an earlier session", async () => {
    eventsApi.leadDashboard.mockReturnValue(new Promise(() => {}));

    const { el } = await mountView(QUEUE_ID, (store) => {
      store.unassigned = [{ event_id: QUEUE_ID, event_name: "Another Lead's Event", status: "submitted", coordinator: null }];
      store.hasSettled = true;
    });

    expect(eventsApi.leadDashboard).toHaveBeenCalledTimes(1);
    expect(el.textContent).not.toContain("Another Lead's Event");
    expect(el.querySelector('[role="status"]').textContent).toMatch(/loading/i);
  });

  it("does not carry a reassign error over from another event", async () => {
    const { el } = await mountView(QUEUE_ID, (store) => {
      store.reassignError = "Left over from the previous event";
    });

    expect(el.textContent).not.toContain("Left over from the previous event");
  });

  it("names the current coordinator of an assigned event", async () => {
    const { el } = await mountView(ASSIGNED_ID);

    expect(el.textContent).toContain("Year-End Dinner");
    expect(el.textContent).toContain("Marcus Lim");
  });

  it("says so, with no reassign control, when the event is not in the Lead's scope", async () => {
    const { el } = await mountView("e0000000-0000-4000-8000-0000000003ff");

    expect(el.textContent).toContain("This event isn't in your scope");
    expect(el.querySelector('a[href="/dashboard/coordinator-lead"]')).not.toBeNull();
    expect(picker(el)).toBeNull();
  });

  it("shows a load failure instead of the event", async () => {
    eventsApi.leadDashboard.mockRejectedValue(new ApiError("Service unavailable", 503));

    const { el } = await mountView(QUEUE_ID);

    expect(el.querySelector('[role="alert"]').textContent).toContain("Service unavailable");
    expect(picker(el)).toBeNull();
  });

  it("offers every coordinator except the current one", async () => {
    const { el } = await mountView(ASSIGNED_ID);

    const values = [...picker(el).querySelectorAll("option")].map((option) => option.value).filter(Boolean);
    expect(values).toEqual(["c2"]);
  });

  it("keeps Reassign disabled until a coordinator is chosen", async () => {
    const { el } = await mountView(QUEUE_ID);
    expect(reassignButton(el).disabled).toBe(true);

    choose(el, "c1");
    await flush();

    expect(reassignButton(el).disabled).toBe(false);
  });

  it("asks for confirmation, then reassigns, announces it and returns to the dashboard", async () => {
    eventsApi.reassign.mockResolvedValue({ id: ASSIGNED_ID });
    const { el, router } = await mountView(ASSIGNED_ID);
    choose(el, "c2");
    await flush();

    reassignButton(el).click();
    await flush();
    expect(eventsApi.reassign).not.toHaveBeenCalled();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("Year-End Dinner");
    expect(dialog.textContent).toContain("Priya Nair");

    document.querySelector('button[aria-label="Reassign"]').click();
    await flush();

    // The version the Lead saw (8), so a screen that is behind is refused rather than overwriting.
    expect(eventsApi.reassign).toHaveBeenCalledWith(ASSIGNED_ID, "c2", 8, "access");
    expect(toastState.value.tone).toBe("success");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-coordinator-lead"));
  });

  it("assigns a queued event through the assign endpoint, not reassign (SCRUM-12)", async () => {
    eventsApi.assign.mockResolvedValue({ id: QUEUE_ID });
    const { el, router } = await mountView(QUEUE_ID);
    choose(el, "c2");
    await flush();
    expect(el.querySelector("h2").textContent).toContain("Assign coordinator");

    reassignButton(el).click();
    await flush();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("Assign event?");
    expect(dialog.textContent).toContain("Priya Nair");

    document.querySelector('button[aria-label="Assign"]').click();
    await flush();

    expect(eventsApi.assign).toHaveBeenCalledWith(QUEUE_ID, "c2", "access");
    expect(eventsApi.reassign).not.toHaveBeenCalled();
    expect(toastState.value.tone).toBe("success");
    expect(toastState.value.message).toContain("assigned to Priya Nair");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-coordinator-lead"));
  });

  it("calls an old event with no coordinator Assign, and sends it through reassign, which accepts it", async () => {
    eventsApi.reassign.mockResolvedValue({ id: QUEUE_ID });
    eventsApi.leadDashboard.mockResolvedValue({ ...PAYLOAD, unassigned: [{ ...PAYLOAD.unassigned[0], status: "planning" }] });
    const { el } = await mountView(QUEUE_ID);
    expect(el.querySelector("h2").textContent).toContain("Assign coordinator");
    expect(reassignButton(el).textContent).toContain("Assign");

    choose(el, "c2");
    await flush();
    reassignButton(el).click();
    await flush();
    expect(document.querySelector('[role="dialog"]').textContent).toContain("Assign event?");
    document.querySelector('button[aria-label="Assign"]').click();
    await flush();

    expect(eventsApi.reassign).toHaveBeenCalledWith(QUEUE_ID, "c2", 3, "access");
    expect(eventsApi.assign).not.toHaveBeenCalled();
  });

  it("shows the second Lead why an event someone else just assigned is refused", async () => {
    eventsApi.assign.mockRejectedValue(new ApiError("This event is already assigned.", 409));
    const { el, router } = await mountView(QUEUE_ID);
    choose(el, "c2");
    await flush();
    reassignButton(el).click();
    await flush();

    document.querySelector('button[aria-label="Assign"]').click();
    await flush();

    expect(el.querySelector('[role="alert"]').textContent).toContain("already assigned");
    expect(router.currentRoute.value.name).toBe("lead-event");
  });

  it("stays on the page and shows why when the server refuses", async () => {
    eventsApi.reassign.mockRejectedValue(new ApiError("This event was updated by someone else. Reload.", 409));
    const { el, router } = await mountView(ASSIGNED_ID);
    choose(el, "c2");
    await flush();
    reassignButton(el).click();
    await flush();

    document.querySelector('button[aria-label="Reassign"]').click();
    await flush();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(el.querySelector('[role="alert"]').textContent).toContain("updated by someone else");
    expect(router.currentRoute.value.name).toBe("lead-event");
  });

  it("closes the dialog without reassigning when the Lead stays", async () => {
    const { el } = await mountView(QUEUE_ID);
    choose(el, "c2");
    await flush();
    reassignButton(el).click();
    await flush();

    document.querySelector('button[aria-label="Cancel"]').click();
    await flush();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(eventsApi.reassign).not.toHaveBeenCalled();
  });
});
