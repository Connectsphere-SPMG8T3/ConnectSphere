import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  venueBookingsApi: { request: vi.fn(), get: vi.fn(), reject: vi.fn(), approve: vi.fn(), restore: vi.fn() },
}));

function booking(overrides = {}) {
  return {
    id: "b1", status: "held", venue_id: "v1", venue_name: "Innovation Lab",
    period: { starts_at: "2031-03-10T06:00:00Z", ends_at: "2031-03-10T09:00:00Z" },
    request_note: "Need early access at 13:00", requested_at: "2031-02-01T00:00:00Z", requested_by_name: "Marcus Lim",
    event: {
      id: "event-1", name: "Partner Summit", status: "planning", expected_attendance: 40,
      layout_preference: "classroom", facilities_required: ["projector", "wifi"], accessibility_needs: "Step-free access",
    },
    decision: null,
    history: [],
    ...overrides,
  };
}

const REJECTED = booking({
  status: "rejected",
  decision: { reason: "Capacity exceeded", suggestion: "Try Heritage Hall", decided_by_name: "Venue Staff",
    decided_at: "2031-03-01T02:00:00Z" },
  history: [{ action: "rejected", from_status: "held", to_status: "rejected", actor_name: "Venue Staff",
    reason: "Capacity exceeded", suggestion: "Try Heritage Hall", at: "2031-03-01T02:00:00Z" }],
});

const mountedApps = [];

async function mountView(response, role = "venue_staff") {
  if (response instanceof Error) venueBookingsApi.get.mockRejectedValue(response);
  else venueBookingsApi.get.mockResolvedValue(response);
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "u1", full_name: "Someone", role };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "booking-request", params: { id: "b1" } });
  const { default: View } = await import("@/views/bookings/BookingRequestView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(venueBookingsApi.get).toHaveBeenCalled());
  await vi.waitFor(() => expect(el.querySelector('[data-testid="booking-loading"]')).toBeNull());
  await nextTick();
  return { el, router };
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

async function typeReason(text) {
  const field = document.getElementById("reject-booking-reason");
  field.value = text;
  field.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("BookingRequestView (SCRUM-38)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    toastState.value = null;
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("CR-104 shows the safety rejection reason to venue staff without a restore action", async () => {
    const { el } = await mountView(booking({ status: "approved", flag: "safety_rejected", flag_reason: "Exits blocked" }));
    const notice = el.querySelector('[data-testid="booking-safety-rejected"]');
    expect(notice).not.toBeNull();
    expect(notice.textContent).toContain("Safety rejected");
    expect(notice.textContent).toContain("Exits blocked");
    expect(button("Restore original booking")).toBeNull();
    expect(notice.querySelector("button")).toBeNull();
  });

  it("AC1 shows venue staff the event's date, time, capacity, layout and other requirements", async () => {
    const { el } = await mountView(booking());

    for (const text of ["Partner Summit", "Innovation Lab", "Mon, 10 Mar 2031, 14:00–17:00", "40", "Classroom",
      "Projector", "Wi-Fi", "Step-free access", "Need early access at 13:00", "Marcus Lim", "Pending hold"]) {
      expect(el.textContent).toContain(text);
    }
    expect(venueBookingsApi.get).toHaveBeenCalledWith("b1", "access");
  });

  it("says when an event left a requirement out", async () => {
    const { el } = await mountView(booking({
      request_note: null,
      event: { id: "event-1", name: "Partner Summit", expected_attendance: null, layout_preference: null,
        facilities_required: [], accessibility_needs: null },
    }));

    expect(el.textContent).toContain("Not specified");
    expect(el.textContent).toContain("No note from the coordinator.");
  });

  it("AC2, AC4 rejects a held booking with a reason and shows the decision", async () => {
    const { el } = await mountView(booking());
    venueBookingsApi.reject.mockResolvedValue(REJECTED);

    button("Reject request").click();
    await nextTick();
    await typeReason("  Capacity exceeded ");
    button("Reject booking request").click();

    await vi.waitFor(() => expect(el.textContent).toContain("Try Heritage Hall"));
    expect(venueBookingsApi.reject).toHaveBeenCalledWith("b1", { reason: "Capacity exceeded", suggestion: null }, "access");
    expect(el.textContent).toContain("Rejected");
    expect(el.textContent).toContain("Capacity exceeded");
    expect(button("Reject request")).toBeNull();
    expect(toastState.value?.message).toBe("Booking rejected. The coordinator has been told.");
  });

  it("AC12 lists the booking's history with who and when", async () => {
    const { el } = await mountView(REJECTED);

    const history = el.querySelector('[data-testid="booking-history"]');
    expect(history.textContent).toContain("Rejected");
    expect(history.textContent).toContain("Venue Staff");
    expect(history.textContent).toContain("1 Mar 2031");
    expect(history.textContent).toContain("Capacity exceeded");
  });

  it("names a system change in the history", async () => {
    const { el } = await mountView(booking({
      status: "expired",
      history: [{ action: "expired", from_status: "held", to_status: "expired", actor_name: null, reason: null,
        suggestion: null, at: "2031-03-03T00:00:00Z" }],
    }));

    const history = el.querySelector('[data-testid="booking-history"]');
    expect(history.textContent).toContain("Expired");
    expect(history.textContent).toContain("System");
  });

  it("has no history section entry when nothing has happened yet", async () => {
    const { el } = await mountView(booking());

    expect(el.querySelector('[data-testid="booking-history"]').textContent).toContain("No decisions yet.");
  });

  it.each(["approved", "re_review", "rejected", "cancelled", "released", "expired"])(
    "AC9 offers no Reject on a %s booking",
    async (status) => {
      await mountView(booking({ status }));

      expect(button("Reject request")).toBeNull();
    },
  );

  it("AC10 explains and reloads when the booking was decided elsewhere first", async () => {
    const { el } = await mountView(booking());
    venueBookingsApi.reject.mockRejectedValue(
      new ApiError("Only a held booking can be rejected. This one is approved.", 409),
    );
    venueBookingsApi.get.mockResolvedValue(booking({ status: "approved" }));

    button("Reject request").click();
    await nextTick();
    await typeReason("Closed");
    button("Reject booking request").click();

    await vi.waitFor(() => expect(el.textContent).toContain("This one is approved."));
    expect(document.getElementById("reject-booking-reason")).toBeNull();
    expect(button("Reject request")).toBeNull();
    expect(el.textContent).toContain("Approved");
  });

  it("keeps the dialog open with the API's message when the text is refused", async () => {
    await mountView(booking());
    venueBookingsApi.reject.mockRejectedValue(new ApiError("Must be 1 to 1000 characters.", 422));

    button("Reject request").click();
    await nextTick();
    await typeReason("Closed");
    button("Reject booking request").click();

    await vi.waitFor(() => expect(document.querySelector('[role="dialog"] [role="alert"]')).not.toBeNull());
    expect(document.querySelector('[role="dialog"] [role="alert"]').textContent).toContain("Must be 1 to 1000 characters.");
  });

  it("closes the dialog on cancel without rejecting", async () => {
    await mountView(booking());

    button("Reject request").click();
    await nextTick();
    button("Cancel").click();
    await nextTick();

    expect(document.getElementById("reject-booking-reason")).toBeNull();
    expect(venueBookingsApi.reject).not.toHaveBeenCalled();
  });

  it("links venue staff back to their dashboard", async () => {
    const { el } = await mountView(booking());

    expect(el.querySelector('a[href="/dashboard/venue-staff"]')).not.toBeNull();
  });

  it("AC6 shows the assigned coordinator the reason, read-only, and links back to the event", async () => {
    const { el } = await mountView(REJECTED, "event_coordinator");

    expect(el.textContent).toContain("Capacity exceeded");
    expect(el.textContent).toContain("Try Heritage Hall");
    expect(button("Reject request")).toBeNull();
    expect(el.querySelector('a[href="/coordinator/events/event-1"]')).not.toBeNull();
  });

  it("says why when the booking can't be shown", async () => {
    const { el } = await mountView(new ApiError("Booking not found.", 404));

    expect(el.textContent).toContain("Booking not found.");
    expect(button("Reject request")).toBeNull();
  });
});

describe("BookingRequestView approve (SCRUM-36)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    toastState.value = null;
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  const APPROVED = booking({
    status: "approved",
    history: [{ action: "approved", from_status: "held", to_status: "approved", actor_name: "Venue Staff",
      reason: null, suggestion: null, at: "2031-03-01T02:00:00Z" }],
  });

  it("AC2, AC10 approves a held booking after confirming, and shows it approved with its history", async () => {
    const { el } = await mountView(booking());
    venueBookingsApi.approve.mockResolvedValue(APPROVED);

    button("Approve request").click();
    await nextTick();
    expect(document.querySelector('[role="dialog"]').textContent).toContain("Approve this booking?");
    expect(venueBookingsApi.approve).not.toHaveBeenCalled();
    button("Approve").click();

    await vi.waitFor(() => expect(toastState.value?.message).toBe("Booking approved. The coordinator has been told."));
    expect(venueBookingsApi.approve).toHaveBeenCalledWith("b1", "access");
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(button("Approve request")).toBeNull();
    expect(button("Reject request")).toBeNull();
    const history = el.querySelector('[data-testid="booking-history"]');
    expect(history.textContent).toContain("Approved");
    expect(history.textContent).toContain("Venue Staff");
    // An approval carries no reason, so there's no "Rejected by venue staff" panel.
    expect(el.querySelector('[data-testid="booking-decision"]')).toBeNull();
  });

  it("closes the confirmation on cancel without approving", async () => {
    await mountView(booking());

    button("Approve request").click();
    await nextTick();
    button("Cancel").click();
    await nextTick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(venueBookingsApi.approve).not.toHaveBeenCalled();
  });

  it("AC6 explains and reloads when the hold expired before approval, showing it Expired", async () => {
    const { el } = await mountView(booking());
    venueBookingsApi.approve.mockRejectedValue(new ApiError("This hold has expired, so it can't be approved.", 409));
    venueBookingsApi.get.mockResolvedValue(booking({ status: "expired" }));

    button("Approve request").click();
    await nextTick();
    button("Approve").click();

    await vi.waitFor(() => expect(el.textContent).toContain("This hold has expired, so it can't be approved."));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(button("Approve request")).toBeNull();
    expect(el.textContent).toContain("Expired");
  });

  it("AC3 explains a refusal that leaves the booking held, and still offers both decisions", async () => {
    const { el } = await mountView(booking());
    venueBookingsApi.approve.mockRejectedValue(new ApiError("Venue blocked for this time.", 409));

    button("Approve request").click();
    await nextTick();
    button("Approve").click();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent).toContain("Venue blocked for this time."));
    expect(button("Approve request")).not.toBeNull();
    expect(button("Reject request")).not.toBeNull();
  });

  it.each(["approved", "re_review", "rejected", "cancelled", "released", "expired"])(
    "AC6 offers no Approve on a %s booking",
    async (status) => {
      await mountView(booking({ status }));

      expect(button("Approve request")).toBeNull();
    },
  );

  it("AC8 offers the coordinator no Approve", async () => {
    await mountView(booking(), "event_coordinator");

    expect(button("Approve request")).toBeNull();
  });
});

describe("BookingRequestView, an affected booking (CR-95 AC9)", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    toastState.value = null;
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  const AFFECTED = booking({ status: "approved", flag: "affected", flag_reason: "Venue unavailable: maintenance" });

  it("tells venue staff why the booking is affected and offers to restore it", async () => {
    const { el } = await mountView(AFFECTED);

    expect(el.querySelector('[data-testid="booking-affected"]').textContent).toContain("Venue unavailable: maintenance");
    expect(button("Restore original booking")).not.toBeNull();
  });

  it("restores the booking and tells staff the coordinator has been told", async () => {
    const { el } = await mountView(AFFECTED);
    venueBookingsApi.restore.mockResolvedValue({ ...AFFECTED, flag: null, flag_reason: null });

    button("Restore original booking").click();

    await vi.waitFor(() => expect(venueBookingsApi.restore).toHaveBeenCalledWith("b1", "access"));
    await vi.waitFor(() => expect(el.querySelector('[data-testid="booking-affected"]')).toBeNull());
    expect(toastState.value.message).toContain("restored");
  });

  it("shows the refusal when the venue isn't free yet", async () => {
    const { el } = await mountView(AFFECTED);
    venueBookingsApi.restore.mockRejectedValue(new ApiError("The venue is still blocked for part of this booking's time.", 409));

    button("Restore original booking").click();

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("still blocked"));
  });

  it("offers a coordinator the reason but not the restore", async () => {
    const { el } = await mountView(AFFECTED, "event_coordinator");

    expect(el.querySelector('[data-testid="booking-affected"]')).not.toBeNull();
    expect(button("Restore original booking")).toBeNull();
  });

  it("shows nothing about a booking that is not affected", async () => {
    const { el } = await mountView(booking({ status: "approved" }));

    expect(el.querySelector('[data-testid="booking-affected"]')).toBeNull();
    expect(button("Restore original booking")).toBeNull();
  });
});
