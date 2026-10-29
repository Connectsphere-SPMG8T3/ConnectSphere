import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// CR-106 AC2, AC5: the Lead sees a coordinator's reassignment request and may decline it.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { leadDashboard: vi.fn(), reassign: vi.fn(), assign: vi.fn(), declineReassignment: vi.fn() },
}));

const WITH_REQUEST = "e0000000-0000-4000-8000-000000001061";
const WITHOUT_REQUEST = "e0000000-0000-4000-8000-000000001062";
const REASON = "I am on leave for the rest of the month";
const MARCUS = { id: "c1", full_name: "Marcus Lim" };
const REQUEST = {
  id: "request-1", kind: "reassignment", status: "open", reason: REASON,
  requested_by: MARCUS, requested_at: "2026-10-27T01:00:00Z",
};

function payload({ withRequest = true } = {}) {
  return {
    unassigned: [],
    active_events: [
      {
        event_id: WITH_REQUEST, event_name: "Year-End Dinner", status: "planning", starts_at: "2026-12-12T02:00:00Z",
        version: 8, organiser_name: "Olivia Tan", coordinator: MARCUS,
        open_reassignment_request: withRequest ? REQUEST : null,
      },
      {
        event_id: WITHOUT_REQUEST, event_name: "Gala Night", status: "confirmed", starts_at: "2026-12-20T02:00:00Z",
        version: 2, organiser_name: "Olivia Tan", coordinator: MARCUS, open_reassignment_request: null,
      },
    ],
    coordinators: [{ ...MARCUS, active_count: 2 }, { id: "c2", full_name: "Priya Nair", active_count: 0 }],
  };
}

const mountedApps = [];

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
    await nextTick();
  }
}

async function mount(viewPath, route) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "l1", full_name: "Joyce Lim", role: "event_coordinator_lead" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push(route);
  const { default: View } = await import(/* @vite-ignore */ viewPath);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await flush();
  return el;
}

const mountEvent = (id) => mount("@/views/events/LeadEventView.vue", { name: "lead-event", params: { id } });
const mountDashboard = () => mount("@/views/dashboards/CoordinatorLeadDashboard.vue", "/dashboard/coordinator-lead");

const button = (root, label) => root.querySelector(`button[aria-label="${label}"]`);
const dialog = () => document.body.querySelector('[role="dialog"]');

async function typeReason(text) {
  const textarea = dialog().querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("CR-106 the Lead sees and declines a reassignment request", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    eventsApi.leadDashboard.mockResolvedValue(payload());
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows who asked and why on the event page (AC2)", async () => {
    const el = await mountEvent(WITH_REQUEST);

    const banner = el.querySelector('[data-testid="reassignment-request-banner"]');
    expect(banner.textContent).toContain("Marcus Lim asked to be reassigned");
    expect(banner.textContent).toContain(REASON);
    expect(button(banner, "Decline request")).not.toBeNull();
  });

  it("shows no banner on an event with no request", async () => {
    const el = await mountEvent(WITHOUT_REQUEST);

    expect(el.querySelector('[data-testid="reassignment-request-banner"]')).toBeNull();
  });

  it("leaves the reassign control in place so the Lead can act on the request (AC3)", async () => {
    const el = await mountEvent(WITH_REQUEST);

    expect(button(el, "Reassign event")).not.toBeNull();
  });

  it("flags the event on the dashboard so the Lead can find it (AC2)", async () => {
    const el = await mountDashboard();

    const flagged = el.querySelector(`[data-lead-event="${WITH_REQUEST}"]`);
    const plain = el.querySelector(`[data-lead-event="${WITHOUT_REQUEST}"]`);
    expect(flagged.textContent).toContain("Reassignment requested");
    expect(plain.textContent).not.toContain("Reassignment requested");
  });

  it("asks first, needs a reason, and sends it trimmed (AC5)", async () => {
    const el = await mountEvent(WITH_REQUEST);
    eventsApi.declineReassignment.mockResolvedValue({ ...REQUEST, status: "declined" });
    eventsApi.leadDashboard.mockResolvedValue(payload({ withRequest: false }));

    button(el, "Decline request").click();
    await nextTick();
    expect(dialog().textContent).toContain("Decline the reassignment request?");
    expect(button(dialog(), "Confirm decline reassignment request").disabled).toBe(true);

    await typeReason("  No other coordinator is free  ");
    button(dialog(), "Confirm decline reassignment request").click();

    await vi.waitFor(() => expect(eventsApi.declineReassignment)
      .toHaveBeenCalledWith(WITH_REQUEST, "No other coordinator is free", "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="reassignment-request-banner"]')).toBeNull());
    expect(dialog()).toBeNull();
  });

  it("keeps the dialog open and shows why the decline was refused", async () => {
    const el = await mountEvent(WITH_REQUEST);
    eventsApi.declineReassignment.mockRejectedValue(
      new ApiError("There is no open reassignment request for this event.", 409),
    );

    button(el, "Decline request").click();
    await nextTick();
    await typeReason("No cover");
    button(dialog(), "Confirm decline reassignment request").click();

    await vi.waitFor(() => expect(dialog().textContent).toContain("no open reassignment request"));
    expect(dialog().querySelector("textarea").value).toBe("No cover");
  });

  it("closes the dialog without sending anything on Go back", async () => {
    const el = await mountEvent(WITH_REQUEST);

    button(el, "Decline request").click();
    await nextTick();
    button(dialog(), "Close").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(eventsApi.declineReassignment).not.toHaveBeenCalled();
  });
});
