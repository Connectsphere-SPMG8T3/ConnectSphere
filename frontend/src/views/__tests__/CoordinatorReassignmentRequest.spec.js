import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// CR-106: the assigned coordinator asks the Lead to reassign their event.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(),
    addComment: vi.fn(), requestReassignment: vi.fn(),
  },
}));

const REASON = "I am on leave for the rest of the month";
const OPEN_REQUEST = {
  id: "request-1", kind: "reassignment", status: "open", reason: REASON,
  requested_by: { id: "c1", full_name: "Marcus Lim" }, requested_at: "2026-10-27T01:00:00Z",
};

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "confirmed", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2099-11-12T02:00:00Z", ends_at: "2099-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    open_cancellation_request: null, open_reassignment_request: null, ...overrides,
  };
}

const mountedApps = [];

async function mountView(response) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  eventsApi.listComments.mockResolvedValue({ comments: [] });
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

const button = (root, label) => root.querySelector(`button[aria-label="${label}"]`);
const dialog = () => document.body.querySelector('[role="dialog"]');

async function typeReason(text) {
  const textarea = dialog().querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("CR-106 coordinator requests a reassignment", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("offers the request on an active event with none open (AC1)", async () => {
    const el = await mountView(eventResponse());

    expect(button(el, "Request reassignment")).not.toBeNull();
    expect(el.querySelector('[data-testid="reassignment-request-banner"]')).toBeNull();
  });

  it("does not offer it on an event a Lead can no longer reassign", async () => {
    const el = await mountView(eventResponse({ status: "completed" }));

    expect(button(el, "Request reassignment")).toBeNull();
  });

  it("shows the pending request instead of a second button (AC5)", async () => {
    const el = await mountView(eventResponse({ open_reassignment_request: OPEN_REQUEST }));

    const banner = el.querySelector('[data-testid="reassignment-request-banner"]');
    expect(banner.textContent).toContain("Reassignment requested");
    expect(banner.textContent).toContain(REASON);
    expect(banner.textContent).toContain("You stay assigned until a Lead acts");
    expect(button(el, "Request reassignment")).toBeNull();
  });

  it("needs a reason, and sends it trimmed (AC1)", async () => {
    const el = await mountView(eventResponse());
    eventsApi.requestReassignment.mockResolvedValue(OPEN_REQUEST);
    eventsApi.get.mockResolvedValue(eventResponse({ open_reassignment_request: OPEN_REQUEST }));

    button(el, "Request reassignment").click();
    await nextTick();
    expect(dialog().textContent).toContain("Ask the Lead to reassign this event?");
    expect(button(dialog(), "Send reassignment request").disabled).toBe(true);

    await typeReason("   ");
    expect(button(dialog(), "Send reassignment request").disabled).toBe(true);

    await typeReason(`  ${REASON}  `);
    button(dialog(), "Send reassignment request").click();

    await vi.waitFor(() => expect(eventsApi.requestReassignment).toHaveBeenCalledWith("event-1", REASON, "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="reassignment-request-banner"]')).not.toBeNull());
    expect(dialog()).toBeNull();
    expect(button(el, "Request reassignment")).toBeNull();
  });

  it("keeps the dialog open and shows the refusal beside the reason", async () => {
    const el = await mountView(eventResponse());
    eventsApi.requestReassignment.mockRejectedValue(
      new ApiError("A reassignment request is already open for this event.", 409),
    );

    button(el, "Request reassignment").click();
    await nextTick();
    await typeReason(REASON);
    button(dialog(), "Send reassignment request").click();

    await vi.waitFor(() => expect(dialog().textContent).toContain("already open"));
    expect(dialog().querySelector("textarea").value).toBe(REASON);
  });

  it("closes the dialog without sending anything on Go back", async () => {
    const el = await mountView(eventResponse());

    button(el, "Request reassignment").click();
    await nextTick();
    button(dialog(), "Close").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(eventsApi.requestReassignment).not.toHaveBeenCalled();
  });
});
