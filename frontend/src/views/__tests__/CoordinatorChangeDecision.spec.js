import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 37: the assigned coordinator approves or rejects the organiser's open change request.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(),
    addComment: vi.fn(), rejectChange: vi.fn(), approveChange: vi.fn(),
    changeImpact: vi.fn().mockResolvedValue({ bookings: [], equipment: [], attendees_notified: 0 }),
  },
  venueBookingsApi: { sendForReReview: vi.fn() },
}));

const OPEN_CHANGE = {
  id: "request-1", kind: "change", status: "open", reason: "More guests confirmed",
  changes: { event: [{ field: "expected_attendance", before: 80, after: 120 }], spaces: [] },
  significant: true,
  requested_by: { id: "o1", full_name: "Priya Nair" }, requested_at: "2026-10-24T01:00:00Z",
};

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "confirmed", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2099-11-12T02:00:00Z", ends_at: "2099-11-12T04:00:00Z", expected_attendance: 80,
    layout_preference: "theatre", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    open_cancellation_request: null, open_change_request: null, ...overrides,
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

describe("Story 37 coordinator decides a change request", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("offers reject on the open change request's banner", async () => {
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));

    const banner = el.querySelector('[data-testid="change-request-banner"]');
    expect(button(banner, "Reject changes")).not.toBeNull();
  });

  it("rejecting needs a reason, sends it trimmed and removes the banner", async () => {
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));
    const kept = eventResponse();
    eventsApi.rejectChange.mockResolvedValue(kept);
    eventsApi.get.mockResolvedValue(kept);

    button(el, "Reject changes").click();
    await nextTick();
    expect(dialog().textContent).toContain("Reject the requested changes?");
    const confirm = button(dialog(), "Reject change request");
    expect(confirm.disabled).toBe(true);

    await typeReason("  The venue can't take more people  ");
    expect(confirm.disabled).toBe(false);
    confirm.click();

    await vi.waitFor(() => expect(eventsApi.rejectChange)
      .toHaveBeenCalledWith("event-1", "The venue can't take more people", "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="change-request-banner"]')).toBeNull());
    expect(dialog()).toBeNull();
  });

  it("approving asks first, then sends the version the coordinator saw", async () => {
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));
    const changed = eventResponse({ expected_attendance: 120, version: 4 });
    eventsApi.approveChange.mockResolvedValue(changed);
    eventsApi.get.mockResolvedValue(changed);

    button(el, "Approve changes").click();
    await nextTick();
    expect(dialog().textContent).toContain("Approve the requested changes?");
    expect(eventsApi.approveChange).not.toHaveBeenCalled();

    [...dialog().querySelectorAll("button")].find((b) => b.textContent.trim() === "Approve changes").click();

    await vi.waitFor(() => expect(eventsApi.approveChange).toHaveBeenCalledWith("event-1", 3, "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="change-request-banner"]')).toBeNull());
  });

  it.each(["confirmed", "preparation", "safety_review"])(
    "warns that a significant change sends a %s event back to Planning", async (status) => {
      const el = await mountView(eventResponse({ status, open_change_request: OPEN_CHANGE }));

      button(el, "Approve changes").click();
      await nextTick();

      expect(dialog().textContent).toContain("The event goes back to Planning and needs a new safety check.");
    });

  it("doesn't warn of a return to Planning for an ordinary change", async () => {
    const el = await mountView(eventResponse({ open_change_request: { ...OPEN_CHANGE, significant: false } }));

    button(el, "Approve changes").click();
    await nextTick();

    expect(dialog().textContent).not.toContain("goes back to Planning");
  });

  it("keeps the dialog open with the error when the rejection is refused", async () => {
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));
    eventsApi.rejectChange.mockRejectedValue(new Error("There is no open change request for this event."));

    button(el, "Reject changes").click();
    await nextTick();
    await typeReason("No room");
    button(dialog(), "Reject change request").click();

    await vi.waitFor(() => expect(dialog().textContent).toContain("There is no open change request for this event."));
  });

  it.each([
    ["conflict", 'The new time clashes with "Product Launch".'],
    ["unsuitable", "After an approved change: Main hall needs 250 people; Grand Ballroom seats 200."],
  ])("offers a replacement for a booking an approved change flagged %s", async (flag, reason) => {
    const el = await mountView(eventResponse({
      status: "planning",
      spaces: [{ id: "space-1", label: "Main hall", expected_pax: 80, layout_preference: "theatre",
        facilities_required: [], starts_at: null, ends_at: null, is_primary: true }],
      venue_bookings: [{ id: "booking-1", event_space_request_id: "space-1", venue_id: "v1",
        venue_name: "Grand Ballroom", status: "approved", expires_at: null, flag, flag_reason: reason,
        replaces_booking_id: null }],
    }));

    const notice = el.querySelector('[data-testid="venue-affected"]');
    expect(notice.textContent).toContain(reason);
    expect([...notice.querySelectorAll("button")].map((b) => b.textContent.trim())).toContain("Find replacement");
  });

  function markedEvent() {
    return eventResponse({
      status: "planning",
      spaces: [{ id: "space-1", label: "Main hall", expected_pax: 80, layout_preference: "theatre",
        facilities_required: [], starts_at: null, ends_at: null, is_primary: true }],
      venue_bookings: [{ id: "booking-1", event_space_request_id: "space-1", venue_id: "v1",
        venue_name: "Grand Ballroom", status: "approved", expires_at: null, flag: null, flag_reason: null,
        replaces_booking_id: null, needs_re_review_reason: "Date or time changed." }],
    });
  }

  it("shows a booking an approved change marked, and why", async () => {
    const el = await mountView(markedEvent());

    const notice = el.querySelector('[data-testid="needs-re-review"]');
    expect(notice.textContent).toContain("Needs re-review");
    expect(notice.textContent).toContain("Date or time changed.");
  });

  it("sends a marked booking to venue staff with an optional note, then reloads", async () => {
    const el = await mountView(markedEvent());
    venueBookingsApi.sendForReReview.mockResolvedValue(null);
    eventsApi.get.mockClear();
    eventsApi.get.mockResolvedValue(eventResponse({ status: "planning" }));

    [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send for re-review").click();
    await nextTick();
    const form = el.querySelector('[role="dialog"][aria-label="Send for re-review"]');
    const textarea = form.querySelector("textarea");
    textarea.value = "  Please check the afternoon  ";
    textarea.dispatchEvent(new Event("input"));
    await nextTick();
    [...form.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send to venue staff").click();

    await vi.waitFor(() => expect(venueBookingsApi.sendForReReview)
      .toHaveBeenCalledWith("booking-1", "Please check the afternoon", "access"));
    await vi.waitFor(() => expect(eventsApi.get).toHaveBeenCalled());
  });

  it("previews what approving would do before the coordinator decides", async () => {
    eventsApi.changeImpact.mockResolvedValueOnce({
      bookings: [{ booking_id: "booking-1", venue_name: "Grand Ballroom", space_label: "Main hall",
        messages: ['Clashes with "Product Launch": it keeps its time and is flagged Conflict.'] }],
      equipment: [{ line_id: "l1", label: "8 × PA Systems", needed: 8, free: 5 }],
      attendees_notified: 3,
    });
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));

    await vi.waitFor(() => expect(el.querySelector('[data-testid="change-impact"]')).not.toBeNull());
    const preview = el.querySelector('[data-testid="change-impact"]');
    expect(eventsApi.changeImpact).toHaveBeenCalledWith("event-1", "access");
    expect(preview.textContent).toContain("If you approve");
    expect(preview.textContent).toContain('Main hall, Grand Ballroom: Clashes with "Product Launch"');
    expect(preview.textContent).toContain("8 × PA Systems: 5 free at the new time.");
    expect(preview.textContent).toContain("3 registered attendees will be told of the new time.");
  });

  it("says when approving changes no arrangement", async () => {
    const el = await mountView(eventResponse({ open_change_request: OPEN_CHANGE }));

    await vi.waitFor(() => expect(el.querySelector('[data-testid="change-impact"]')).not.toBeNull());
    expect(el.querySelector('[data-testid="change-impact"]').textContent)
      .toContain("No venue booking or equipment needs anything from staff.");
  });
});

