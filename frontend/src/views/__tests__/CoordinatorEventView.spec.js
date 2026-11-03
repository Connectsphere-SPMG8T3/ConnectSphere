import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, eventsApi, registrationsApi, venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  venueBookingsApi: { markRevised: vi.fn() },
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  registrationsApi: { managedEvent: vi.fn() },
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
const currentStep = (el) => el.querySelector('ol[aria-label="Event progress"] [aria-current="step"]')?.textContent ?? "";

describe("CoordinatorEventView (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
    registrationsApi.managedEvent.mockResolvedValue({
      event_id: "event-1",
      effective_capacity: null,
      registered_count: 0,
      remaining_places: null,
      waitlist_count: 0,
      registrations: [],
    });
  });

  it("goes back to the Events view, not the dashboard Overview", async () => {
    const el = await mountView(eventResponse({ status: "planning" }));
    const back = [...el.querySelectorAll("button")].find((node) => node.textContent.trim() === "Back to events");
    expect(back).toBeTruthy();
    expect(el.textContent).not.toContain("Back to dashboard");

    back.click();
    const { default: router } = await import("@/router");
    await vi.waitFor(() => expect(router.currentRoute.value.query).toEqual({ tab: "events" }));
    expect(router.currentRoute.value.name).toBe("dashboard-coordinator");
  });

  it("shows assigned coordinators attendee contacts after registration is disabled (SCRUM-35)", async () => {
    registrationsApi.managedEvent.mockResolvedValue({
      effective_capacity: 20,
      registered_count: 1,
      remaining_places: 19,
      waitlist_count: 0,
      registrations: [
        { id: "registration-1", full_name: "Attendee Name", status: "registered", email: "attendee@example.test", phone_number: "+65 8000 0001" },
      ],
    });
    const el = await mountView(eventResponse({ registration_enabled: false }));

    await vi.waitFor(() => expect(el.textContent).toContain("attendee@example.test"));
    expect(registrationsApi.managedEvent).toHaveBeenCalledWith("event-1", "access");
    expect(el.textContent).toContain("Attendee Name");
    expect(el.textContent).toContain("+65 8000 0001");
  });

  it("labels the return action Ask for amendment, and its dialog to match", async () => {
    await mountView(eventResponse({ status: "under_review" }));
    expect(button("Open return dialog").textContent.trim()).toBe("Ask for amendment");
    button("Open return dialog").click();
    await nextTick();
    expect(document.querySelector("#return-modal-title").textContent.trim()).toBe("Ask for amendment?");
  });

  it("puts the review actions beside the title, above the progress bar", async () => {
    const el = await mountView(eventResponse({ status: "under_review" }));
    const actions = el.querySelector('[data-testid="review-actions"]');
    const title = el.querySelector("h1");
    const progress = el.querySelector('ol[aria-label="Event progress"]');
    expect(actions.contains(button("Approve request"))).toBe(true);
    expect(actions.parentElement).toBe(title.parentElement.parentElement);
    expect(actions.compareDocumentPosition(progress) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the status as a progress bar in the header instead of a badge", async () => {
    const el = await mountView(eventResponse({ status: "under_review" }));
    const progress = el.querySelector('ol[aria-label="Event progress"]');
    expect(progress).not.toBeNull();
    expect(progress.querySelector('[aria-current="step"]').textContent).toContain("Under review");
    expect(el.querySelector('[data-testid="status-outcome"]')).toBeNull();
  });

  it("shows the request ID in Request details rather than the top bar", async () => {
    const el = await mountView(eventResponse());
    const details = el.querySelector('[data-testid="request-details-card"]');
    const id = details.querySelector('[data-testid="request-id"]');
    expect(id?.textContent.trim()).toBe("event-1");
    expect(el.textContent.match(/event-1/g)).toHaveLength(1);
  });

  it("names the organiser and their organisation first in Request details (SCRUM-49 AC3, D82)", async () => {
    const el = await mountView(eventResponse({ organiser: { full_name: "Olivia Tan", organisation_name: "Tan & Partners Events" } }));
    const details = el.querySelector('[data-testid="request-details-card"]');
    expect(details.querySelector('[data-testid="organiser-name"]')?.textContent.trim()).toBe("Olivia Tan");
    expect(details.querySelector('[data-testid="organiser-organisation"]')?.textContent.trim()).toBe("Tan & Partners Events");
    const labels = [...details.querySelectorAll("dt")].map((node) => node.textContent.trim());
    expect(labels.slice(0, 2)).toEqual(["Organiser", "Organisation"]);
  });

  it("shows Not provided when the organiser has no organisation (SCRUM-49 AC3)", async () => {
    const el = await mountView(eventResponse({ organiser: { full_name: "Olivia Tan", organisation_name: null } }));
    const details = el.querySelector('[data-testid="request-details-card"]');
    expect(details.querySelector('[data-testid="organiser-organisation"]')?.textContent.trim()).toBe("Not provided");
  });

  it("shows the equipment request inside the Request details card", async () => {
    const el = await mountView(eventResponse());
    const details = el.querySelector('[data-testid="request-details-card"]');
    expect(details).not.toBeNull();
    expect(details.querySelector("#equipment-request-title")).not.toBeNull();
  });

  it("puts Discussion and History together in the last row, with Discussion wider", async () => {
    const el = await mountView(eventResponse());
    const row = el.querySelector('[data-testid="discussion-history-row"]');
    const discussion = el.querySelector('[data-testid="discussion-card"]');
    const history = el.querySelector('[data-testid="history-card"]');
    expect(row).not.toBeNull();
    expect(row.parentElement.lastElementChild).toBe(row);
    expect(row.classList.contains("lg:col-span-2")).toBe(true);
    expect(row.classList.contains("lg:grid-cols-3")).toBe(true);
    expect([...row.children]).toEqual([discussion, history]);
    expect(discussion.classList.contains("lg:col-span-2")).toBe(true);
    expect(history.classList.contains("lg:col-span-2")).toBe(false);
  });

  it.each([false,true])('CR-104 shows the rejected booking and revises it (spaces=%s)', async (multi) => {
    const rejected={id:'b1',venue_id:'v1',venue_name:'Town Hall',status:'approved',flag:'safety_rejected',flag_reason:'Exits blocked',event_space_request_id:'s1'};
    const other={id:'b2',venue_id:'v2',venue_name:'Other Hall',status:'approved',event_space_request_id:'s2'};
    const response=eventResponse({status:'planning',venue_booking:rejected,venue_bookings:[rejected,other],
      spaces:multi?[{id:'s1',label:'Hall A'},{id:'s2',label:'Hall B'}]:[]});
    const el=await mountView(response);
    expect(el.querySelectorAll('[data-testid=venue-safety-rejected]')).toHaveLength(1);
    if(multi) {
      const cards=el.querySelectorAll('article');
      const otherCard=[...cards].find(card=>card.textContent.includes('Hall B'));
      expect(otherCard.querySelector('[data-testid=venue-safety-rejected]')).toBeNull();
    }
    venueBookingsApi.markRevised.mockResolvedValue({id:'b1',flag:null});
    eventsApi.get.mockResolvedValue({...response,venue_booking:{...rejected,flag:null},venue_bookings:[{...rejected,flag:null},other]});
    const previous=eventsApi.get.mock.calls.length;
    el.querySelector('[data-testid=venue-safety-rejected] button').click();
    await nextTick();
    const input=el.querySelector('[role=dialog] textarea'); input.value='Moved the barriers'; input.dispatchEvent(new Event('input')); await nextTick();
    [...el.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Mark as revised').click();
    await vi.waitFor(()=>expect(venueBookingsApi.markRevised).toHaveBeenCalledWith('b1','Moved the barriers','access'));
    await vi.waitFor(()=>expect(eventsApi.get.mock.calls.length).toBeGreaterThan(previous));
    await vi.waitFor(()=>expect(el.querySelector('[data-testid=venue-safety-rejected]')).toBeNull());
    expect(toastState.value.message).toBe('Marked revised. Send the event for safety check when everything is ready.');
  });
  it('CR-104 shows a refused revision in the page', async()=>{
    const rejected={id:'b1',venue_id:'v1',status:'approved',flag:'safety_rejected',flag_reason:'Exits blocked'};
    const el=await mountView(eventResponse({status:'planning',venue_booking:rejected,venue_bookings:[rejected]}));
    venueBookingsApi.markRevised.mockRejectedValue(new ApiError('Only in Planning',409));
    el.querySelector('[data-testid=venue-safety-rejected] button').click();
    await nextTick();
    const input=el.querySelector('[role=dialog] textarea'); input.value='Moved the barriers'; input.dispatchEvent(new Event('input')); await nextTick();
    [...el.querySelectorAll('[role=dialog] button')].find(b=>b.textContent==='Mark as revised').click();
    await vi.waitFor(()=>expect(el.querySelector('[role=alert]').textContent).toBe('Only in Planning'));
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
    const latest = { id: "d1", decision: "arrangement_rejected", organiser_comment: "Replace this venue", private_note: "Hall manager is difficult", checklist: [{factor: "emergency_access", booking_id: "b1", venue_name: "Town Hall", rating: "concern", note: "Only one exit"}], decided_by_name: "Officer Lee",
      decided_at: "2026-10-08T02:00:00Z", affected_booking_ids: ["b1"], affected_equipment_request_ids: ["q1"], rejected_venue_ids: ["v1"], rejected_venues: [{venue_id:"v1",venue_name:"Town Hall"}], affected_bookings:[{booking_id:"b1",venue_name:"Town Hall"}], affected_equipment:[{id:"q1",equipment_name:"Projector"}] };
    const earlier = { ...latest, id: "d0", decision: "changes_requested", organiser_comment: "Keep the aisle clear", private_note: null, checklist: [] };
    eventsApi.safetyDecisions.mockResolvedValue([latest, earlier]);
    const el = await mountView(eventResponse({ status: "planning", latest_safety_decision: latest,
      venue_booking: { id: "b1", venue_id: "v1", venue_name: "Town Hall", status: "released" } }));
    await vi.waitFor(() => expect(el.textContent).toContain("Keep the aisle clear"));
    for (const text of ["Safety Officer's decision", "Arrangement rejected", "Replace this venue", "Officer Lee", "8 Oct", "Rejected venue: Town Hall", "Concerns: Town Hall · Projector",
      // CR-108 AC5: the coordinator sees the organiser comment, the private notes and the checklist.
      "Comment for the organiser", "Private notes", "Hall manager is difficult", "Emergency access: Concern", "Only one exit"]) expect(el.textContent).toContain(text);
    expect(eventsApi.safetyDecisions).toHaveBeenCalledWith("event-1", "access");
  });
  it("CR-104 identifies rejected bookings even when the released booking is absent from the event read", async () => {
    const decision = { id: "d1", decision: "arrangement_rejected", organiser_comment: "Replace it", decided_by_name: "Officer Lee", decided_at: "2026-10-08T02:00:00Z", affected_booking_ids: ["released-booking"], affected_equipment_request_ids: [], rejected_venue_ids: ["v1"], rejected_venues: [{venue_id:"v1",venue_name:null}] };
    eventsApi.safetyDecisions.mockResolvedValue([decision]);
    const el = await mountView(eventResponse({ status: "planning", latest_safety_decision: decision, venue_booking: null }));
    await vi.waitFor(() => expect(el.textContent).toContain("Safety decision history"));
    const banner = [...el.querySelectorAll('div')].find((item) => item.textContent.includes("Safety Officer's decision") && item.textContent.includes('Rejected venue: a venue that no longer exists'));
    expect(banner?.textContent).toContain("Rejected venue: a venue that no longer exists");
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
    button("Send").click(); await vi.waitFor(() => expect(currentStep(el)).toContain("Safety review"));
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

  // CR-95 AC3, AC4: an affected booking says so, why, and how to replace it.
  describe("an affected venue booking (CR-95)", () => {
    const AFFECTED = {
      id: "b-affected", event_space_request_id: null, venue_id: "v1", venue_name: "Seminar Room 1",
      status: "approved", flag: "affected", flag_reason: "Venue unavailable: Maintenance",
    };
    const REPLACEMENT = {
      id: "b-new", event_space_request_id: null, venue_id: "v2", venue_name: "Heritage Hall",
      status: "held", flag: null, replaces_booking_id: "b-affected", expires_at: "2026-11-01T04:00:00Z",
    };
    const findReplacement = (root) => [...root.querySelectorAll("button")].find((b) => b.textContent.trim() === "Find replacement");

    it.each(["planning", "safety_review", "confirmed"])(
      "shows why a %s event's venue is unavailable and opens venue search to replace it",
      async (status) => {
        const el = await mountView(eventResponse({ status, venue_booking: AFFECTED, venue_bookings: [AFFECTED] }));

        const panel = el.querySelector('[data-testid="venue-panel"]');
        expect(panel.textContent).toContain("Seminar Room 1");
        expect(panel.textContent).toContain("Needs alternative venue");
        expect(panel.textContent).toContain("Venue unavailable: Maintenance");
        findReplacement(panel).click();
        const { default: router } = await import("@/router");
        await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("venue-search"));
        expect(router.currentRoute.value.query).toEqual({ event: "event-1", replaces: "b-affected" });
      },
    );

    it("shows the replacement asked for and offers no second one", async () => {
      const el = await mountView(eventResponse({
        status: "planning", venue_booking: REPLACEMENT, venue_bookings: [AFFECTED, REPLACEMENT],
      }));

      const panel = el.querySelector('[data-testid="venue-panel"]');
      expect(panel.textContent).toContain("Seminar Room 1");
      expect(panel.textContent).toContain("Replacement requested");
      expect(panel.querySelector('[data-testid="venue-replacement"]').textContent).toContain("Heritage Hall");
      expect(panel.querySelector('[data-testid="venue-replacement"]').textContent).toContain("Tentative hold");
      expect(findReplacement(panel)).toBeUndefined();
    });

    it("offers no replacement once the event is past planning, review and confirmation", async () => {
      const el = await mountView(eventResponse({ status: "returned", venue_bookings: [AFFECTED] }));

      const panel = el.querySelector('[data-testid="venue-panel"]');
      expect(panel.textContent).toContain("Needs alternative venue");
      expect(findReplacement(panel)).toBeUndefined();
    });

    it("marks an affected space's booking on its own card and replaces it from there", async () => {
      const spaceBooking = { ...AFFECTED, event_space_request_id: "space-b" };
      const el = await mountView(eventResponse({
        status: "confirmed", spaces: TWO_SPACES, venue_bookings: [
          { id: "b1", event_space_request_id: "space-a", venue_id: "v3", venue_name: "Innovation Lab", status: "approved" },
          spaceBooking,
        ],
      }));

      const [main, breakout] = spaceCards(el);
      expect(main.textContent).not.toContain("Needs alternative venue");
      expect(breakout.textContent).toContain("Needs alternative venue");
      expect(breakout.textContent).toContain("Venue unavailable: Maintenance");
      findReplacement(breakout).click();
      const { default: router } = await import("@/router");
      await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("venue-search"));
      expect(router.currentRoute.value.query).toEqual({ event: "event-1", space: "space-b", replaces: "b-affected" });
    });
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

  it("CR-97 leaves bookings to the space cards when the event has spaces, keeping rejections in the Venue panel", async () => {
    const booking = { id: "b1", event_space_request_id: "space-a", venue_id: "v1", venue_name: "Innovation Lab", status: "approved" };
    const el = await mountView(eventResponse({
      status: "planning", spaces: TWO_SPACES, venue_booking: booking, venue_bookings: [booking],
      rejected_bookings: [{ id: "b9", venue_id: "v3", venue_name: "Auditorium A", reason: "Closed for works", suggestion: null, decided_at: null }],
    }));
    const panel = el.querySelector('[data-testid="venue-panel"]');
    expect(panel.textContent).toContain("Auditorium A");
    expect(panel.textContent).not.toContain("Innovation Lab");
    expect(panel.textContent).not.toContain("Find a venue");
  });

  it("CR-97 still explains why no venue can be requested yet when the event has spaces", async () => {
    const el = await mountView(eventResponse({ status: "under_review", spaces: TWO_SPACES }));
    expect(el.querySelector('[data-testid="venue-panel"]').textContent)
      .toContain("A venue can be requested once the request is approved for planning.");
  });

  it("CR-97 keeps CR-99 AC7's expired-hold explanation on the space card", async () => {
    const el = await mountView(eventResponse({
      status: "planning", spaces: TWO_SPACES,
      venue_bookings: [{ id: "b2", event_space_request_id: "space-b", venue_id: "v2", venue_name: "Heritage Hall",
        status: "expired", expires_at: "2031-06-01T04:00:00Z" }],
    }));
    const breakout = spaceCards(el)[1];
    expect(breakout.querySelector('[data-testid="hold-expired"]').textContent).toContain(
      "The hold expired on 1 Jun 2031, 12:00 before venue staff approved it.",
    );
    expect(breakout.textContent).toContain("You can request this venue again if it's still free, or find another.");
  });

  it.each([[1, "1 space"], [2, "2 spaces"]])("counts %i space(s) as \"%s\"", async (count, label) => {
    const el = await mountView(eventResponse({ status: "planning", spaces: TWO_SPACES.slice(0, count) }));
    expect(el.querySelector('[data-testid="space-count"]').textContent.trim()).toBe(label);
  });

  // A space the booking trigger created ("Main space") has a label only.
  it("shows only the requirements a space has, and says when it has none", async () => {
    const el = await mountView(eventResponse({ status: "planning", spaces: [
      { id: "space-a", label: "Main space", expected_pax: null, layout_preference: null, facilities_required: [] },
      { id: "space-b", label: "Breakout room", expected_pax: 20, layout_preference: null, facilities_required: [] },
    ] }));
    const requirements = spaceCards(el).map((card) => card.querySelector('[data-testid="space-requirements"]').textContent.trim());
    expect(requirements).toEqual(["Requirements not specified", "20 pax"]);
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
    await vi.waitFor(() => expect(currentStep(el)).toContain("Planning"));
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


describe("CoordinatorEventView technical preparation (CR-110 AC4)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("shows the stage, the internal note and who set it", async () => {
    const el = await mountView(eventResponse({ status: "preparation",
      technical_preparation: { stage: "completed", note: "Cables run", updated_at: "2026-10-26T03:00:00Z", updated_by_name: "Tan Wei" } }));

    const card = el.querySelector('[data-testid="technical-preparation-summary"]').textContent;
    expect(card).toContain("Completed");
    expect(card).toContain("Cables run");
    expect(card).toContain("Tan Wei");
  });

  it("shows nothing when the API sends no stage", async () => {
    const el = await mountView(eventResponse({ status: "planning" }));

    expect(el.querySelector('[data-testid="technical-preparation-summary"]')).toBeNull();
  });
});
