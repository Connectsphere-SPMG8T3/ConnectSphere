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

  it.each(["planning", "confirmed", "preparation"])("offers a direct cancel for a %s event", async (status) => {
    const el = await mountView(eventResponse({ status }));

    expect(button(el, "Cancel event")).not.toBeNull();
  });

  it.each(["under_review", "returned", "safety_review", "cancelled", "completed"])(
    "offers no direct cancel for a %s event", async (status) => {
      const el = await mountView(eventResponse({ status }));

      expect(button(el, "Cancel event")).toBeNull();
    },
  );

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
});
