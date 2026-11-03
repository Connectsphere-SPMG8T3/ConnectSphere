import { afterEach, describe, expect, it, vi } from "vitest";

import { authApi, equipmentApi, eventsApi, notificationsApi, registrationsApi, venueBookingsApi } from "@/services/api";

describe("SCRUM-92 profile update API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("patches only the current profile using the authenticated session", async () => {
    const accessToken = "access-token";
    const profile = { id: "user-1", full_name: "New Name", phone_number: null };
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => profile });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      authApi.updateProfile(accessToken, { full_name: "New Name", phone_number: null }),
    ).resolves.toEqual(profile);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/me",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ full_name: "New Name", phone_number: null }),
        headers: expect.objectContaining({ Authorization: `Bearer ${accessToken}` }),
      }),
    );
  });
});

describe("Story 43 public registration API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads public events and registers with the attendee session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ events: [] }) })
      .mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ id: "event/one" }) })
      .mockResolvedValueOnce({ status: 201, ok: true, json: async () => ({ status: "registered" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(registrationsApi.directory()).resolves.toEqual({ events: [] });
    await expect(registrationsApi.event("event/one")).resolves.toEqual({ id: "event/one" });
    await expect(registrationsApi.register("event/one", "attendee-token")).resolves.toEqual({ status: "registered" });

    expect(fetchMock.mock.calls.map(([url, options]) => [url, options.method, options.headers.Authorization])).toEqual([
      ["http://localhost:8000/api/v1/public/events", "GET", undefined],
      ["http://localhost:8000/api/v1/public/events/event%2Fone", "GET", undefined],
      ["http://localhost:8000/api/v1/public/events/event%2Fone/registrations", "POST", "Bearer attendee-token"],
    ]);
  });
});

describe("Story 56 attendee registrations API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the signed-in attendee's registrations", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ registrations: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(registrationsApi.myRegistrations("attendee-token")).resolves.toEqual({
      registrations: [],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/registrations/me",
      expect.objectContaining({ method: "GET" }),
    );
  });
});

describe("SCRUM-55 attendee withdrawal API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts an authenticated withdrawal request with an encoded event id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ registration_id: "registration-1", status: "withdrawn" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(registrationsApi.withdraw("event/one", "attendee-token")).resolves.toEqual({
      registration_id: "registration-1",
      status: "withdrawn",
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/registrations/event%2Fone/withdraw");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer attendee-token");
  });
});

describe("SCRUM-86 waitlist API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("accepts an invitation and leaves the waitlist with the attendee session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({ registration_id: "registration-1", status: "registered" }),
      })
      .mockResolvedValueOnce({ status: 204, ok: true, json: async () => null });
    vi.stubGlobal("fetch", fetchMock);

    await expect(registrationsApi.acceptInvitation("registration-1", "attendee-token")).resolves.toEqual({
      registration_id: "registration-1",
      status: "registered",
    });
    await expect(registrationsApi.leaveWaitlist("registration-1", "attendee-token")).resolves.toBeNull();

    expect(fetchMock.mock.calls.map(([, options]) =>
      options.headers.Authorization?.endsWith("attendee-token"),
    )).toEqual([true, true]);
    expect(fetchMock.mock.calls.map(([, options]) =>
      options.headers.Authorization === "Bearer attendee-token",
    )).toEqual([true, true]);
    expect(fetchMock.mock.calls.map(([url, options]) => [url, options.method])).toEqual([
      ["http://localhost:8000/api/v1/registrations/registration-1/accept", "POST"],
      ["http://localhost:8000/api/v1/registrations/registration-1", "DELETE"],
    ]);
    expect(fetchMock.mock.calls.every(([, options]) =>
      options.headers.Authorization?.endsWith("attendee-token"),
    )).toBe(true);
  });
});

describe("SCRUM-35 managed registrations API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads an event registration report with the active manager session", async () => {
    const report = { registered_count: 2, registrations: [] };
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => report,
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(registrationsApi.managedEvent("event/one", "manager-token")).resolves.toEqual(report);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/events/event%2Fone/registrations");
    expect(options.method).toBe("GET");
    expect(options.headers.Authorization.endsWith("manager-token")).toBe(true);
  });
});

describe("eventsApi.clone", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an authenticated clone request with an encoded event id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      ok: true,
      json: async () => ({ id: "clone-1", status: "draft" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(eventsApi.clone("event/one", "access-token")).resolves.toEqual({
      id: "clone-1",
      status: "draft",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/events/event%2Fone/clone",
      expect.objectContaining({
        method: "POST",
        body: undefined,
        headers: expect.objectContaining({ Authorization: "Bearer access-token" }),
      }),
    );
  });

  it("surfaces a clone denial as an ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 404,
      ok: false,
      json: async () => ({ detail: "Event not found." }),
    }));

    await expect(eventsApi.clone("missing-event", "access-token")).rejects.toMatchObject({
      message: "Event not found.",
      status: 404,
    });
  });
});

describe("CR-98 space request API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts, patches and deletes space requests with encoded route ids", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ status: 201, ok: true, json: async () => ({ id: "space-1" }) })
      .mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ id: "space-1" }) })
      .mockResolvedValueOnce({ status: 204, ok: true, json: async () => null });
    vi.stubGlobal("fetch", fetchMock);

    await expect(eventsApi.createSpace("event/one", { label: "Main venue" }, "token")).resolves.toEqual({ id: "space-1" });
    await expect(eventsApi.updateSpace("event/one", "space/one", { label: "Updated" }, "token")).resolves.toEqual({ id: "space-1" });
    await expect(eventsApi.removeSpace("event/one", "space/one", "token")).resolves.toBeNull();

    expect(fetchMock.mock.calls.map(([url, options]) => [url, options.method, options.body])).toEqual([
      ["http://localhost:8000/api/v1/events/event%2Fone/spaces", "POST", JSON.stringify({ label: "Main venue" })],
      ["http://localhost:8000/api/v1/events/event%2Fone/spaces/space%2Fone", "PATCH", JSON.stringify({ label: "Updated" })],
      ["http://localhost:8000/api/v1/events/event%2Fone/spaces/space%2Fone", "DELETE", undefined],
    ]);
    expect(fetchMock.mock.calls.every(([, options]) => options.headers.Authorization === "Bearer token")).toBe(true);
  });

  it("posts a booking request scoped to one space", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 201, ok: true, json: async () => ({ id: "booking-1" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(venueBookingsApi.request({ event_space_request_id: "space-1", venue_id: "venue-1", note: null }, "token"))
      .resolves.toEqual({ id: "booking-1" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ event_space_request_id: "space-1", venue_id: "venue-1", note: null }),
        headers: expect.objectContaining({ Authorization: "Bearer token" }),
      }),
    );
  });
});

describe("SCRUM-21 a refused booking request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps what is in the way beside the message", async () => {
    const conflict = {
      kind: "booking", event_name: "Alumni Night", block_reason: null,
      starts_at: "2031-04-07T01:30:00Z", ends_at: "2031-04-07T04:45:00Z",
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 409,
      ok: false,
      json: async () => ({ detail: "Venue already held for this time by another event.", conflict }),
    }));

    await expect(venueBookingsApi.request({ venue_id: "venue-1" }, "token")).rejects.toMatchObject({
      message: "Venue already held for this time by another event.",
      status: 409,
      conflict,
    });
  });

  it("has no conflict when the API names none", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 409, ok: false, json: async () => ({ detail: "This venue is inactive." }),
    }));

    await expect(venueBookingsApi.request({ venue_id: "venue-1" }, "token")).rejects.toMatchObject({ conflict: null });
  });
});

describe("SCRUM-82 eventsApi.sendForSafetyCheck", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("posts to the encoded endpoint without a body and uses the session token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({status: 200, ok: true, json: async () => ({status: "safety_review"})});
    vi.stubGlobal("fetch", fetchMock);
    await expect(eventsApi.sendForSafetyCheck("event/one", "access-token")).resolves.toEqual({status: "safety_review"});
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/v1/events/event%2Fone/send-for-safety-check", expect.objectContaining({method: "POST", body: undefined, headers: expect.objectContaining({Authorization: "Bearer access-token"})}));
  });
});

// CR-103 / CR-104: exact Safety Officer request contracts.
describe('safety decision API contracts', () => {
  afterEach(() => vi.unstubAllGlobals());
  it.each([
    ['safetyQueue', '/events/safety-queue', 'GET', false],
    ['safetyHistory', '/events/safety-history', 'GET', false],
    ['safetyReview', '/events/event%2Fone/safety-review', 'GET', false],
    ['safetyDecisions', '/events/event%2Fone/safety-decisions', 'GET', false],
    ['safetyApprove', '/events/event%2Fone/safety-approve', 'POST', true],
    ['safetyRequestChanges', '/events/event%2Fone/safety-request-changes', 'POST', true],
    ['safetyReject', '/events/event%2Fone/safety-reject', 'POST', true],
  ])('%s sends the documented authenticated request', async (name, path, method, hasBody) => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 'result' }) });
    vi.stubGlobal('fetch', fetchMock);
    expect(eventsApi[name], `${name} is implemented`).toBeTypeOf('function');
    const body = { comment: 'Crowd flow', booking_ids: ['b1'], equipment_request_ids: ['q1'] };
    const result = ['safetyQueue', 'safetyHistory'].includes(name) ? await eventsApi[name]('access')
      : hasBody ? await eventsApi[name]('event/one', body, 'access') : await eventsApi[name]('event/one', 'access');
    expect(result).toEqual({ id: 'result' });
    expect(fetchMock).toHaveBeenCalledWith(`http://localhost:8000/api/v1${path}`, {
      method, body: hasBody ? JSON.stringify(body) : undefined,
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer access' },
    });
  });
});

describe("CR-99 venueBookingsApi.changeExpiry", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("patches the encoded booking's expiry with the session token", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ status: "held" }) });
    vi.stubGlobal("fetch", fetchMock);

    await venueBookingsApi.changeExpiry("d/1", { expires_at: "2031-08-05T12:00:00+08:00" }, "access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings/d%2F1/expiry",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ expires_at: "2031-08-05T12:00:00+08:00" }),
        headers: expect.objectContaining({ Authorization: "Bearer access-token" }),
      }),
    );
  });
});

describe("SCRUM-38 venueBookingsApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reads one booking request by its encoded id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ id: "b/1" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(venueBookingsApi.get("b/1", "token")).resolves.toEqual({ id: "b/1" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings/b%2F1",
      expect.objectContaining({ method: "GET", headers: expect.objectContaining({ Authorization: "Bearer token" }) }),
    );
  });

  it("posts a rejection with its reason and suggestion", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ status: "rejected" }) });
    vi.stubGlobal("fetch", fetchMock);
    const payload = { reason: "Capacity exceeded", suggestion: null };

    await venueBookingsApi.reject("b1", payload, "token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings/b1/reject",
      expect.objectContaining({ method: "POST", body: JSON.stringify(payload) }),
    );
  });

  it("SCRUM-36 posts an approval with no body to the encoded id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ status: "approved" }) });
    vi.stubGlobal("fetch", fetchMock);

    await expect(venueBookingsApi.approve("b/1", "token")).resolves.toEqual({ status: "approved" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings/b%2F1/approve",
      expect.objectContaining({
        method: "POST", body: undefined, headers: expect.objectContaining({ Authorization: "Bearer token" }),
      }),
    );
  });
});

describe("eventsApi Lead calls (CR-101)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(payload) {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => payload });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("reads the Lead dashboard with the caller's token", async () => {
    const fetchMock = stubFetch({ unassigned: [] });

    await expect(eventsApi.leadDashboard("access-token")).resolves.toEqual({ unassigned: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/events/dashboard/lead",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer access-token" }) }),
    );
  });

  it("posts the coordinator id and the version the Lead saw, with an encoded event id", async () => {
    const fetchMock = stubFetch({ id: "event/one" });

    await eventsApi.reassign("event/one", "c2", 4, "access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/events/event%2Fone/reassign",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ coordinator_id: "c2", expected_version: 4 }) }),
    );
  });

  it("reads an event's reassignment history with an encoded event id (SCRUM-81)", async () => {
    const fetchMock = stubFetch({ entries: [] });

    await eventsApi.reassignmentHistory("event/one", "access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/events/event%2Fone/reassignment-history",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer access-token" }) }),
    );
  });

  it("assigns a queued event with only the coordinator id (SCRUM-12)", async () => {
    const fetchMock = stubFetch({ id: "event/one" });

    await eventsApi.assign("event/one", "c2", "access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/events/event%2Fone/assign",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ coordinator_id: "c2" }) }),
    );
  });
});

describe("venueBookingsApi.restore (CR-95 AC9)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an authenticated restore for the encoded booking id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200, ok: true, json: async () => ({ id: "booking/1", flag: null }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(venueBookingsApi.restore("booking/1", "token")).resolves.toEqual({ id: "booking/1", flag: null });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/venue-bookings/booking%2F1/restore",
      expect.objectContaining({ method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }) }),
    );
  });
});

describe('CR-104 mark revised API', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('POSTs the encoded booking id with the revision note', async () => {
    const fetchMock=vi.fn().mockResolvedValue({status:200,ok:true,json:async()=>({id:'b1',flag:null})});
    vi.stubGlobal('fetch',fetchMock);
    expect(venueBookingsApi.markRevised).toBeTypeOf('function');
    await expect(venueBookingsApi.markRevised('b/1','Moved the barriers','token')).resolves.toEqual({id:'b1',flag:null});
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/venue-bookings/b%2F1/mark-revised',expect.objectContaining({method:'POST',body:JSON.stringify({note:'Moved the barriers'}),headers:expect.objectContaining({Authorization:'Bearer token'})}));
  });
});

describe("notificationsApi (SCRUM-113)", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(body) {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => body });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }
  const authed = expect.objectContaining({ Authorization: "Bearer token" });

  it("reads the unread count", async () => {
    const fetchMock = stubFetch({ count: 2, latest_at: "t" });

    await expect(notificationsApi.unreadCount("token")).resolves.toEqual({ count: 2, latest_at: "t" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/notifications/unread-count",
      expect.objectContaining({ method: "GET", headers: authed }),
    );
  });

  it("lists a page, sending only the paging it is given", async () => {
    const fetchMock = stubFetch({ items: [], next_before: null });

    await notificationsApi.list({ limit: 20 }, "token");
    await notificationsApi.list({ limit: 20, before: "cur=" }, "token");
    await notificationsApi.list(undefined, "token");

    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls).toEqual([
      "http://localhost:8000/api/v1/notifications?limit=20",
      "http://localhost:8000/api/v1/notifications?limit=20&before=cur%3D",
      "http://localhost:8000/api/v1/notifications",
    ]);
  });

  it("marks one read with an encoded id, and all read", async () => {
    const fetchMock = stubFetch({ id: "n/1", read: true });

    await notificationsApi.markRead("n/1", "token");
    await notificationsApi.markAllRead("token");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/notifications/n%2F1/read",
      expect.objectContaining({ method: "POST", headers: authed }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/notifications/read-all",
      expect.objectContaining({ method: "POST", headers: authed }),
    );
  });
});

describe("Story 115 cancellation decisions", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts approve, reject and direct cancel with the coordinator's session", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ id: "event/one" }) });
    vi.stubGlobal("fetch", fetchMock);

    await eventsApi.approveCancellation("event/one", "token");
    await eventsApi.rejectCancellation("event/one", "Venue already paid", "token");
    await eventsApi.cancelEvent("event/one", "No replacement venue", "token");

    expect(fetchMock.mock.calls.map(([url, options]) => [url, options.method, options.body])).toEqual([
      ["http://localhost:8000/api/v1/events/event%2Fone/cancellation-request/approve", "POST", undefined],
      ["http://localhost:8000/api/v1/events/event%2Fone/cancellation-request/reject", "POST",
        JSON.stringify({ reason: "Venue already paid" })],
      ["http://localhost:8000/api/v1/events/event%2Fone/cancel", "POST", JSON.stringify({ reason: "No replacement venue" })],
    ]);
    expect(fetchMock.mock.calls.every(([, options]) => options.headers.Authorization === "Bearer token")).toBe(true);
  });
});

describe("Story 32 change requests", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the proposal with the organiser's session", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 201, ok: true, json: async () => ({ id: "r1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const body = { reason: "More seats", version: 3, event: { expected_attendance: 120 }, spaces: [] };

    await eventsApi.requestChange("event/one", body, "token");

    const [[url, options]] = fetchMock.mock.calls;
    expect([url, options.method, options.body, options.headers.Authorization]).toEqual([
      "http://localhost:8000/api/v1/events/event%2Fone/change-request", "POST", JSON.stringify(body), "Bearer token",
    ]);
  });
});

// Story 37: the change decision and re-review requests.
describe("story 37 change decision and re-review API", () => {
  afterEach(() => vi.unstubAllGlobals());
  it.each([
    ["eventsApi.changeImpact", () => eventsApi.changeImpact("event/one", "access"), "/events/event%2Fone/change-request/impact", "GET", undefined],
    ["eventsApi.approveChange", () => eventsApi.approveChange("event/one", 3, "access"), "/events/event%2Fone/change-request/approve", "POST", { version: 3 }],
    ["eventsApi.rejectChange", () => eventsApi.rejectChange("event/one", "No room", "access"), "/events/event%2Fone/change-request/reject", "POST", { reason: "No room" }],
    ["venueBookingsApi.sendForReReview", () => venueBookingsApi.sendForReReview("b/1", "Check it", "access"), "/venue-bookings/b%2F1/send-for-re-review", "POST", { note: "Check it" }],
    ["equipmentApi.sendLineForReReview", () => equipmentApi.sendLineForReReview("l/1", null, "access"), "/equipment/requests/l%2F1/send-for-re-review", "POST", { note: null }],
  ])("%s sends the documented authenticated request", async (name, call, path, method, body) => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "result" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(call()).resolves.toEqual({ id: "result" });
    expect(fetchMock).toHaveBeenCalledWith(`http://localhost:8000/api/v1${path}`, {
      method, body: body === undefined ? undefined : JSON.stringify(body),
      headers: { "Content-Type": "application/json", Authorization: "Bearer access" },
    });
  });
});
// SCRUM-44: the coordinator changes or removes an equipment line and reads its history.
describe("SCRUM-44 equipment line change API", () => {
  afterEach(() => vi.unstubAllGlobals());
  it.each([
    ["equipmentApi.updateLine", () => equipmentApi.updateLine("l/1", { quantity: 2, expected_status: "pending" }, "access"),
      "/equipment/requests/l%2F1", "PATCH", { quantity: 2, expected_status: "pending" }],
    ["equipmentApi.removeLine", () => equipmentApi.removeLine("l/1", "re_review", "access"),
      "/equipment/requests/l%2F1?expected_status=re_review", "DELETE", undefined],
    ["equipmentApi.eventHistory", () => equipmentApi.eventHistory("event/one", "access"),
      "/equipment/requests/event/event%2Fone/history", "GET", undefined],
  ])("%s sends the documented authenticated request", async (name, call, path, method, body) => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "result" }) });
    vi.stubGlobal("fetch", fetchMock);
    await expect(call()).resolves.toEqual({ id: "result" });
    expect(fetchMock).toHaveBeenCalledWith(`http://localhost:8000/api/v1${path}`, {
      method, body: body === undefined ? undefined : JSON.stringify(body),
      headers: { "Content-Type": "application/json", Authorization: "Bearer access" },
    });
  });
});
