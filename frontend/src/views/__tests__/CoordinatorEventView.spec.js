import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn() },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "under_review", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-11-12T02:00:00Z", ends_at: "2026-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    ...overrides,
  };
}

const mountedApps = [];

async function mountView(response) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "c1", full_name: "Marcus Lim", role: "event_coordinator" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "coordinator-event", params: { id: response.id } });
  const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

describe("CoordinatorEventView (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("offers approve and reject for a request under review", async () => {
    const el = await mountView(eventResponse());

    expect(el.textContent).toContain("Under review");
    expect(button("Approve request")).not.toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it("offers only reject while planning", async () => {
    await mountView(eventResponse({ status: "planning" }));

    expect(button("Approve request")).toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it.each(["returned", "confirmed", "rejected", "cancelled", "completed", "submitted"])(
    "offers no decision when the request is %s",
    async (status) => {
      await mountView(eventResponse({ status }));

      expect(button("Approve request")).toBeNull();
      expect(button("Open reject dialog")).toBeNull();
    },
  );

  it("approves after confirmation and shows Planning", async () => {
    const el = await mountView(eventResponse());
    eventsApi.approve.mockResolvedValue(eventResponse({ status: "planning", version: 4 }));

    button("Approve request").click();
    await nextTick();
    expect(document.body.textContent).toContain("This does not confirm the event");
    button("Approve").click();

    await vi.waitFor(() => expect(eventsApi.approve).toHaveBeenCalledWith("event-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Planning"));
    expect(button("Approve request")).toBeNull();
  });

  it("rejects with the typed reason", async () => {
    const el = await mountView(eventResponse());
    eventsApi.reject.mockResolvedValue(eventResponse({ status: "rejected", version: 4 }));

    button("Open reject dialog").click();
    await nextTick();
    const textarea = document.querySelector("textarea");
    textarea.value = "Venue unavailable";
    textarea.dispatchEvent(new Event("input"));
    await nextTick();
    button("Reject request").click();

    await vi.waitFor(() => expect(eventsApi.reject).toHaveBeenCalledWith("event-1", "Venue unavailable", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Rejected"));
  });

  it("shows why the page can't load", async () => {
    eventsApi.get.mockRejectedValue(Object.assign(new Error("Only the event's assigned coordinator can do this."), { status: 403 }));
    eventsApi.history.mockResolvedValue({ entries: [] });
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore();
    auth.token = "access";
    auth.profile = { id: "c9", full_name: "Other", role: "event_coordinator" };
    auth.sessionVerified = true;
    const { default: router } = await import("@/router");
    await router.push({ name: "coordinator-event", params: { id: "event-1" } });
    const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp(View).use(pinia).use(router);
    app.mount(el);
    mountedApps.push(app);

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("assigned coordinator"));
  });

  it("reloads when the route param id changes", async () => {
    const el = await mountView(eventResponse({ id: "event-1", name: "First Event" }));
    eventsApi.get.mockResolvedValue(eventResponse({ id: "event-2", name: "Second Event" }));

    const { default: router } = await import("@/router");
    await router.push({ name: "coordinator-event", params: { id: "event-2" } });

    await vi.waitFor(() => expect(el.textContent).toContain("Second Event"));
  });
});

