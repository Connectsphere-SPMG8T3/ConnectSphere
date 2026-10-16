import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn(), returnForAmendment: vi.fn(), sendForSafetyCheck: vi.fn(), listComments: vi.fn(), addComment: vi.fn(), setPrimarySpace: vi.fn(), clearPrimarySpace: vi.fn() },
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

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

describe("CoordinatorEventView (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("SCRUM-38 AC6, AC7 shows why venue staff rejected a booking and still offers another venue", async () => {
    const el = await mountView(eventResponse({
      status: "planning", venue_booking: null,
      rejected_bookings: [{ id: "b9", venue_id: "v1", venue_name: "Innovation Lab", reason: "Capacity exceeded",
        suggestion: "Try Heritage Hall", decided_at: "2026-10-08T02:00:00Z" }],
    }));

    const panel = el.querySelector('[data-testid="venue-panel"]');
    for (const text of ["Rejected by venue staff", "Innovation Lab", "Capacity exceeded", "Try Heritage Hall", "8 Oct"]) {
      expect(panel.textContent).toContain(text);
    }
    expect(panel.querySelector('a[href="/bookings/b9"]')).not.toBeNull();
    expect(panel.textContent).toContain("Find a venue");
  });

  it("SCRUM-38 lists a rejection that predates recorded reasons without inventing one", async () => {
    const el = await mountView(eventResponse({
      status: "planning", venue_booking: null,
      rejected_bookings: [{ id: "b8", venue_id: "v2", venue_name: null, reason: null, suggestion: null, decided_at: null }],
    }));

    const panel = el.querySelector('[data-testid="venue-panel"]');
    expect(panel.textContent).toContain("Rejected by venue staff");
    expect(panel.textContent).toContain("No reason was recorded.");
  });

  it("CR-104 shows the latest private decision and the full decision history", async () => {
    const latest = { id: "d1", decision: "arrangement_rejected", comment: "Replace this venue", decided_by_name: "Officer Lee",
      decided_at: "2026-10-08T02:00:00Z", affected_booking_ids: ["b1"], affected_equipment_request_ids: ["q1"], rejected_venue_ids: ["v1"] };
    const earlier = { ...latest, id: "d0", decision: "changes_requested", comment: "Keep the aisle clear" };
    eventsApi.safetyDecisions.mockResolvedValue([latest, earlier]);
    const el = await mountView(eventResponse({ status: "planning", latest_safety_decision: latest,
      venue_booking: { id: "b1", venue_id: "v1", venue_name: "Town Hall", status: "released" } }));
    await vi.waitFor(() => expect(el.textContent).toContain("Keep the aisle clear"));
    for (const text of ["Safety Officer's decision", "Arrangement rejected", "Replace this venue", "Officer Lee", "8 Oct", "Affected bookings: 1", "Affected equipment requests: 1", "Rejected by the Safety Officer"]) expect(el.textContent).toContain(text);
    expect(eventsApi.safetyDecisions).toHaveBeenCalledWith("event-1", "access");
  });
  it("CR-104 identifies rejected bookings even when the released booking is absent from the event read", async () => {
    const decision = { id: "d1", decision: "arrangement_rejected", comment: "Replace it", decided_by_name: "Officer Lee", decided_at: "2026-10-08T02:00:00Z", affected_booking_ids: ["released-booking"], affected_equipment_request_ids: [], rejected_venue_ids: ["v1"] };
    eventsApi.safetyDecisions.mockResolvedValue([decision]);
    const el = await mountView(eventResponse({ status: "planning", latest_safety_decision: decision, venue_booking: null }));
    await vi.waitFor(() => expect(el.textContent).toContain("Safety decision history"));
    const banner = [...el.querySelectorAll('div')].find((item) => item.textContent.includes("Safety Officer's decision") && item.textContent.includes('Affected bookings: 1'));
    expect(banner?.textContent).toContain("Rejected by the Safety Officer");
    expect(el.textContent).not.toContain('released-booking');
    expect(el.textContent).not.toContain('v1');
  });

  it.each(["under_review", "safety_review", "confirmed", "rejected"])("CR-104 hides the latest banner while %s", async (status) => {
    const el = await mountView(eventResponse({ status, latest_safety_decision: { decision: "changes_requested", comment: "Private latest", decided_at: "2026-10-08T02:00:00Z" } }));
    expect(el.textContent).not.toContain("Safety Officer's decision");
    expect(el.textContent).not.toContain("Private latest");
  });

  it("SCRUM-82 disables send and names missing arrangements", async () => {
    const el = await mountView(eventResponse({status: "planning", safety_readiness: {ready: false, missing: ["Technical status is not Ready."]}, registration_enabled: true, registration_capacity: 80}));
    const send = button("Send for safety check"); expect(send.disabled).toBe(true);
    expect(document.getElementById(send.getAttribute("aria-describedby")).textContent).toContain("Technical status is not Ready.");
    expect(el.textContent).toContain("For information"); expect(el.textContent).toContain("80");
  });
  it("SCRUM-82 sends after confirmation and removes coordinator actions", async () => {
    const el = await mountView(eventResponse({status: "planning", safety_readiness: {ready: true, missing: []}}));
    eventsApi.sendForSafetyCheck.mockResolvedValue(eventResponse({status: "safety_review"}));
    button("Send for safety check").click(); await nextTick();
    expect(document.body.textContent).toContain("Send for safety check?");
    button("Send").click(); await vi.waitFor(() => expect(el.textContent).toContain("Safety review"));
    expect(button("Send for safety check")).toBeNull(); expect(eventsApi.sendForSafetyCheck).toHaveBeenCalledTimes(1);
    expect(toastState.value.message).toBe("Sent for safety check");
  });
  it("SCRUM-82 refreshes missing arrangements after a stale-page refusal", async () => {
    const ready = eventResponse({status: "planning", safety_readiness: {ready: true, missing: []}});
    const el = await mountView(ready);
    eventsApi.sendForSafetyCheck.mockRejectedValue(new ApiError("Not ready for safety check: Technical status is not Ready.", 409));
    eventsApi.get.mockResolvedValue({...ready, safety_readiness: {ready: false, missing: ["Technical status is not Ready."]}});
    button("Send for safety check").click(); await nextTick(); button("Send").click();
    await vi.waitFor(() => expect(button("Send for safety check").disabled).toBe(true));
    expect(el.textContent).toContain("Not ready for safety check: Technical status is not Ready.");
    expect(eventsApi.get).toHaveBeenCalledTimes(2);
  });
  it("SCRUM-82 has no send or information block during safety review", async () => {
    const el = await mountView(eventResponse({status: "safety_review"}));
    expect(button("Send for safety check")).toBeNull(); expect(el.textContent).not.toContain("For information");
  });
  it("CR-99 shows when a held venue's hold expires", async () => {
    const el = await mountView(eventResponse({ status: "planning", venue_booking: {
      id: "b1", venue_id: "v1", venue_name: "Innovation Lab", status: "held", expires_at: "2026-11-01T04:00:00Z" } }));

    expect(el.querySelector('[data-testid="hold-expiry"]').textContent)
      .toContain("Hold expires 1 Nov 2026, 12:00 unless approved.");
  });

  it("CR-99 AC7 shows an expired hold and offers the venue search again", async () => {
    const el = await mountView(eventResponse({ status: "planning", venue_booking: {
      id: "b1", venue_id: "v1", venue_name: "Innovation Lab", status: "expired", expires_at: "2026-11-01T04:00:00Z" } }));

    const panel = el.querySelector('[data-testid="venue-panel"]');
    expect(panel.textContent).toContain("Expired");
    expect(panel.textContent).toContain("The hold expired on 1 Nov 2026, 12:00");
    expect([...panel.querySelectorAll("button")].map((b) => b.textContent.trim())).toContain("Find a venue");
  });

  it("shows the event's discussion thread (SCRUM-61)", async () => {
    const el = await mountView(eventResponse());

    await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access"));
    expect(el.textContent).toContain("Discussion");
  });

  it("shows facilities for each proposed space", async () => {
    const el = await mountView(eventResponse({ status: "planning",
      spaces: [
        { id: "space-a", label: "Main hall", expected_pax: 80, layout_preference: "theatre", facilities_required: ["projector"], starts_at: "2026-11-12T05:00:00Z", ends_at: "2026-11-12T08:00:00Z" },
        { id: "space-b", label: "Breakout room", expected_pax: 20, layout_preference: "classroom", facilities_required: ["whiteboard"], starts_at: null, ends_at: null },
      ],
    }));

    const spaceSection = el.querySelector('[data-testid="event-spaces"]');
    expect(spaceSection.textContent).toContain("projector");
    expect(spaceSection.textContent).toContain("whiteboard");
    const requestDetailLabels = [...el.querySelectorAll("dt")].map((node) => node.textContent.trim());
    expect(requestDetailLabels).not.toContain("Preferred layout");
    expect(requestDetailLabels).not.toContain("Facilities");
    expect(spaceSection.textContent).toContain("1:00 pm");
    expect(spaceSection.textContent).toContain("4:00 pm");
    expect(spaceSection.textContent).toContain("Uses event schedule");
    expect(el.textContent).toContain("Starts");
    expect(el.textContent).toContain("Ends");
    expect([...spaceSection.querySelectorAll("a")].map((link) => link.getAttribute("href"))).toEqual([
      "/venues?event=event-1&space=space-a",
      "/venues?event=event-1&space=space-b",
    ]);
  });

  // CR-97 AC5: the event page lists every space's booking and its status.
  const TWO_SPACES = [
    { id: "space-a", label: "Main hall", expected_pax: 50, layout_preference: "theatre", facilities_required: [], is_primary: false },
    { id: "space-b", label: "Breakout room", expected_pax: 20, layout_preference: "classroom", facilities_required: [], is_primary: false },
  ];
  const spaceCards = (el) => [...el.querySelectorAll('[data-testid="event-spaces"] article')];

  it("CR-97 AC5 shows each space's own booking and status", async () => {
    const el = await mountView(eventResponse({
      status: "planning", spaces: TWO_SPACES,
      venue_bookings: [
        { id: "b1", event_space_request_id: "space-a", venue_id: "v1", venue_name: "Innovation Lab", status: "approved" },
        { id: "b2", event_space_request_id: "space-b", venue_id: "v2", venue_name: "Heritage Hall", status: "held",
          expires_at: "2026-11-01T02:00:00Z" },
      ],
    }));
    const [main, breakout] = spaceCards(el);
    expect(main.textContent).toContain("Innovation Lab");
    expect(main.textContent).toContain("Approved");
    expect(breakout.textContent).toContain("Heritage Hall");
    expect(breakout.textContent).toContain("Tentative hold");
    expect(breakout.textContent).toContain("Hold expires");
  });

  it("CR-97 offers Find venue only for a space without an occupying booking", async () => {
    const el = await mountView(eventResponse({
      status: "planning", spaces: [...TWO_SPACES, { id: "space-c", label: "Foyer", expected_pax: 30, facilities_required: [] }],
      venue_bookings: [
        { id: "b1", event_space_request_id: "space-a", venue_id: "v1", venue_name: "Innovation Lab", status: "held" },
        { id: "b2", event_space_request_id: "space-b", venue_id: "v2", venue_name: "Heritage Hall", status: "expired",
          expires_at: "2026-10-01T02:00:00Z" },
      ],
    }));
    const findVenue = (card) => [...card.querySelectorAll("a")].some((link) => link.textContent.trim() === "Find venue");
    expect(spaceCards(el).map(findVenue)).toEqual([false, true, true]);
  });

  it("CR-97 AC9 badges the primary space only", async () => {
    const el = await mountView(eventResponse({
      status: "planning", spaces: [TWO_SPACES[0], { ...TWO_SPACES[1], is_primary: true }],
    }));
    const badged = (card) => card.querySelector('[data-testid="primary-badge"]') !== null;
    expect(spaceCards(el).map(badged)).toEqual([false, true]);
    expect(spaceCards(el)[1].querySelector('[data-testid="primary-badge"]').textContent.trim()).toBe("Primary venue");
  });

  it("CR-97 AC9 makes a space the primary venue", async () => {
    const el = await mountView(eventResponse({ status: "planning", spaces: TWO_SPACES }));
    eventsApi.setPrimarySpace.mockResolvedValue(eventResponse({
      status: "planning", spaces: [TWO_SPACES[0], { ...TWO_SPACES[1], is_primary: true }],
    }));
    spaceCards(el)[1].querySelector('button[aria-label="Make Breakout room the primary venue"]').click();
    await vi.waitFor(() => expect(spaceCards(el)[1].querySelector('[data-testid="primary-badge"]')).not.toBeNull());
    expect(eventsApi.setPrimarySpace).toHaveBeenCalledWith("event-1", "space-b", "access");
  });

  it("CR-97 AC9 unsets the primary venue", async () => {
    const el = await mountView(eventResponse({ status: "planning", spaces: [{ ...TWO_SPACES[0], is_primary: true }, TWO_SPACES[1]] }));
    eventsApi.clearPrimarySpace.mockResolvedValue(eventResponse({ status: "planning", spaces: TWO_SPACES }));
    spaceCards(el)[0].querySelector('button[aria-label="Unset Main hall as the primary venue"]').click();
    await vi.waitFor(() => expect(el.querySelector('[data-testid="primary-badge"]')).toBeNull());
    expect(eventsApi.clearPrimarySpace).toHaveBeenCalledWith("event-1", "access");
  });

  it.each([
    ["an event with one space", { status: "planning", spaces: [{ ...TWO_SPACES[0], is_primary: true }] }],
    ["an event outside planning", { status: "safety_review", spaces: TWO_SPACES }],
  ])("CR-97 AC9 offers no primary choice for %s", async (_, overrides) => {
    const el = await mountView(eventResponse(overrides));
    expect(el.querySelector('[data-testid="event-spaces"] button')).toBeNull();
  });

  it("does not offer space venue search before planning", async () => {
    const el = await mountView(eventResponse({
      status: "under_review",
      spaces: [{ id: "space-a", label: "Main hall", expected_pax: 80, layout_preference: "theatre", facilities_required: [] }],
    }));

    expect(el.querySelector('[data-testid="event-spaces"] a')).toBeNull();
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
      expect(button("Open return dialog")).toBeNull();
    },
  );

  it("offers return for a request under review, and not while planning", async () => {
    await mountView(eventResponse());
    expect(button("Open return dialog")).not.toBeNull();

    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    await mountView(eventResponse({ status: "planning" }));
    expect(button("Open return dialog")).toBeNull();
  });

  it("returns the request with the message and flagged fields, then shows it waiting on the organiser", async () => {
    const el = await mountView(eventResponse());
    eventsApi.returnForAmendment.mockResolvedValue(eventResponse({
      status: "returned", version: 4,
      amendment: { id: "a1", message: "Confirm attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" },
    }));

    button("Open return dialog").click();
    await nextTick();
    const textarea = document.querySelector('[role="dialog"] textarea');
    textarea.value = "Confirm attendance";
    textarea.dispatchEvent(new Event("input"));
    const box = [...document.querySelectorAll('input[type="checkbox"]')]
      .find((input) => input.closest("label").textContent.includes("Expected attendance"));
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    await nextTick();
    button("Return request").click();

    await vi.waitFor(() => expect(eventsApi.returnForAmendment).toHaveBeenCalledWith(
      "event-1", { message: "Confirm attendance", flagged_fields: ["expected_attendance"] }, "access",
    ));
    await vi.waitFor(() => expect(el.textContent).toContain("Waiting for the organiser to amend"));
    expect(el.textContent).toContain("Returned for amendment");
    expect(button("Approve request")).toBeNull();
    expect(button("Open return dialog")).toBeNull();
  });

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
    const textarea = document.querySelector('[role="dialog"] textarea');
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

