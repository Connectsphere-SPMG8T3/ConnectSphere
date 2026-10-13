import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn() },
}));

const QUEUE_ID = "e0000000-0000-4000-8000-000000000301";
const ASSIGNED_ID = "e0000000-0000-4000-8000-000000000302";

const PAYLOAD = {
  unassigned: [
    {
      event_id: QUEUE_ID, event_name: "Partner Summit", status: "under_review", starts_at: "2026-11-12T02:00:00Z",
      organiser_name: "Olivia Tan", purpose: "Quarterly partner meeting", expected_attendance: 12,
      coordinator: null, assigned_at: null,
    },
  ],
  active_events: [
    {
      event_id: ASSIGNED_ID, event_name: "Year-End Dinner", status: "planning", starts_at: "2026-12-12T02:00:00Z",
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

async function mountView(eventId) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "l1", full_name: "Joyce Lim", role: "event_coordinator_lead" };
  auth.sessionVerified = true;

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
    expect(el.textContent).toContain("Under review");
    expect(el.textContent).toContain("Olivia Tan");
    expect(el.textContent).toContain("Quarterly partner meeting");
    expect(el.textContent).toContain("Unassigned");
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
    eventsApi.reassign.mockResolvedValue({ id: QUEUE_ID });
    const { el, router } = await mountView(QUEUE_ID);
    choose(el, "c2");
    await flush();

    reassignButton(el).click();
    await flush();
    expect(eventsApi.reassign).not.toHaveBeenCalled();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog.textContent).toContain("Partner Summit");
    expect(dialog.textContent).toContain("Priya Nair");

    document.querySelector('button[aria-label="Reassign"]').click();
    await flush();

    expect(eventsApi.reassign).toHaveBeenCalledWith(QUEUE_ID, "c2", "access");
    expect(toastState.value.tone).toBe("success");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("dashboard-coordinator-lead"));
  });

  it("stays on the page and shows why when the server refuses", async () => {
    eventsApi.reassign.mockRejectedValue(new ApiError("This event was updated by someone else. Reload.", 409));
    const { el, router } = await mountView(QUEUE_ID);
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
