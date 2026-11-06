import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 115: the assigned coordinator approves or rejects the open request, or cancels directly.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(),
    addComment: vi.fn(), approveCancellation: vi.fn(), rejectCancellation: vi.fn(), cancelEvent: vi.fn(),
  },
}));

const REQUEST_REASON = "Our keynote speaker has withdrawn";
const OPEN_REQUEST = {
  id: "request-1", kind: "cancellation", status: "open", reason: REQUEST_REASON,
  requested_by: { id: "o1", full_name: "Priya Nair" }, requested_at: "2026-10-23T01:00:00Z",
};

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "confirmed", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2099-11-12T02:00:00Z", ends_at: "2099-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    open_cancellation_request: null, ...overrides,
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

function button(root, label) {
  return root.querySelector(`button[aria-label="${label}"]`);
}

function dialog() {
  return document.body.querySelector('[role="dialog"]');
}

async function typeReason(text) {
  const textarea = dialog().querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("Story 115 coordinator decides a cancellation", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("offers approve and reject on the open request's banner", async () => {
    const el = await mountView(eventResponse({ open_cancellation_request: OPEN_REQUEST }));

    const banner = el.querySelector('[data-testid="cancellation-request-banner"]');
    expect(button(banner, "Approve cancellation")).not.toBeNull();
    expect(button(banner, "Reject cancellation")).not.toBeNull();
  });

  it("approving asks first, then cancels the event and shows it cancelled", async () => {
    const el = await mountView(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    const cancelled = eventResponse({ status: "cancelled" });
    eventsApi.approveCancellation.mockResolvedValue(cancelled);
    eventsApi.get.mockResolvedValue(cancelled);

    button(el, "Approve cancellation").click();
    await nextTick();
    expect(dialog().textContent).toContain("Approve the cancellation?");
    expect(eventsApi.approveCancellation).not.toHaveBeenCalled();

    [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim() === "Cancel the event").click();

    await vi.waitFor(() => expect(eventsApi.approveCancellation).toHaveBeenCalledWith("event-1", "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="cancellation-request-banner"]')).toBeNull());
  });

  it("rejecting needs a reason and sends it trimmed", async () => {
    const el = await mountView(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    const kept = eventResponse();
    eventsApi.rejectCancellation.mockResolvedValue(kept);
    eventsApi.get.mockResolvedValue(kept);

    button(el, "Reject cancellation").click();
    await nextTick();
    const confirm = button(dialog(), "Reject cancellation request");
    expect(confirm.disabled).toBe(true);

    await typeReason("  The venue is already paid for  ");
    expect(confirm.disabled).toBe(false);
    confirm.click();

    await vi.waitFor(() => expect(eventsApi.rejectCancellation)
      .toHaveBeenCalledWith("event-1", "The venue is already paid for", "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="cancellation-request-banner"]')).toBeNull());
    expect(dialog()).toBeNull();
  });

  it.each(["confirmed", "preparation"])("offers a direct cancel for a %s event", async (status) => {
    const el = await mountView(eventResponse({ status }));

    expect(button(el, "Cancel event")).not.toBeNull();
  });

  it.each(["under_review", "returned", "planning", "safety_review", "cancelled", "completed"])(
    "offers no direct cancel for a %s event", async (status) => {
      const el = await mountView(eventResponse({ status }));

      expect(button(el, "Cancel event")).toBeNull();
    },
  );

  // 115-R AC1: before confirmation the coordinator rejects; from confirmation, cancels.
  it.each([
    ["under_review", true, false],
    ["planning", true, false],
    ["safety_review", false, false],
    ["confirmed", false, true],
    ["preparation", false, true],
  ])("a %s event offers Reject %s and Cancel event %s, never both", async (status, reject, cancel) => {
    const el = await mountView(eventResponse({ status }));

    expect(button(el, "Open reject dialog") !== null).toBe(reject);
    expect(button(el, "Cancel event") !== null).toBe(cancel);
  });

  // 115-R AC3: the open request is answered first, through its banner.
  it.each(["under_review", "planning", "confirmed", "preparation"])(
    "a %s event with an open request offers only the banner's decisions", async (status) => {
      const el = await mountView(eventResponse({ status, open_cancellation_request: OPEN_REQUEST }));

      expect(button(el, "Open reject dialog")).toBeNull();
      expect(button(el, "Cancel event")).toBeNull();
      expect(button(el, "Approve cancellation")).not.toBeNull();
      expect(button(el, "Reject cancellation")).not.toBeNull();
    },
  );

  it("keeps the other header actions while a request is open", async () => {
    const el = await mountView(eventResponse({ status: "planning", open_cancellation_request: OPEN_REQUEST }));

    expect(button(el, "Request reassignment")).not.toBeNull();
    expect(button(el, "Edit event details")).not.toBeNull();
  });

  // 115-R AC4: rejecting the request gives the header action back.
  it("offers Reject again once the request is rejected", async () => {
    const el = await mountView(eventResponse({ status: "planning", open_cancellation_request: OPEN_REQUEST }));
    eventsApi.rejectCancellation.mockResolvedValue(eventResponse({ status: "planning" }));
    eventsApi.get.mockResolvedValue(eventResponse({ status: "planning" }));

    button(el, "Reject cancellation").click();
    await nextTick();
    await typeReason("The venue is already paid for");
    button(dialog(), "Reject cancellation request").click();

    await vi.waitFor(() => expect(button(el, "Open reject dialog")).not.toBeNull());
  });

  it("offers no direct cancel once the event has started", async () => {
    const el = await mountView(eventResponse({ starts_at: "2020-01-01T00:00:00Z" }));

    expect(button(el, "Cancel event")).toBeNull();
  });

  it("cancelling directly sends the coordinator's reason", async () => {
    const el = await mountView(eventResponse());
    const cancelled = eventResponse({ status: "cancelled" });
    eventsApi.cancelEvent.mockResolvedValue(cancelled);
    eventsApi.get.mockResolvedValue(cancelled);

    button(el, "Cancel event").click();
    await nextTick();
    await typeReason("No replacement venue could be found");
    button(dialog(), "Confirm cancel event").click();

    await vi.waitFor(() => expect(eventsApi.cancelEvent)
      .toHaveBeenCalledWith("event-1", "No replacement venue could be found", "access"));
    await vi.waitFor(() => expect(button(el, "Cancel event")).toBeNull());
  });

  it("keeps the dialog open with the refusal beside the reason", async () => {
    const el = await mountView(eventResponse());
    eventsApi.cancelEvent.mockRejectedValue(
      Object.assign(new Error("This event has already started, so it can't be cancelled."), { status: 409 }));

    button(el, "Cancel event").click();
    await nextTick();
    await typeReason("Too late");
    button(dialog(), "Confirm cancel event").click();

    await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]').textContent)
      .toContain("This event has already started, so it can't be cancelled."));
  });

  it("shows a refused approval in the page", async () => {
    const el = await mountView(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    eventsApi.approveCancellation.mockRejectedValue(
      Object.assign(new Error("This event was updated by someone else. Reload."), { status: 409 }));

    button(el, "Approve cancellation").click();
    await nextTick();
    [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim() === "Cancel the event").click();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent)
      .toContain("This event was updated by someone else. Reload."));
  });

  it("keeps a refused rejection in its dialog", async () => {
    const el = await mountView(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    eventsApi.rejectCancellation.mockRejectedValue(
      Object.assign(new Error("There is no open cancellation request for this event."), { status: 409 }));

    button(el, "Reject cancellation").click();
    await nextTick();
    await typeReason("Not now");
    button(dialog(), "Reject cancellation request").click();

    await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]').textContent)
      .toContain("There is no open cancellation request for this event."));
  });

  it.each([
    ["Reject cancellation", { open_cancellation_request: OPEN_REQUEST }],
    ["Cancel event", {}],
  ])("closes the %s dialog without sending anything", async (label, overrides) => {
    const el = await mountView(eventResponse(overrides));

    button(el, label).click();
    await nextTick();
    button(dialog(), "Close").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(eventsApi.rejectCancellation).not.toHaveBeenCalled();
    expect(eventsApi.cancelEvent).not.toHaveBeenCalled();
  });
});

