import { afterEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";

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
    const result = name === 'safetyQueue' ? await eventsApi[name]('access')
      : hasBody ? await eventsApi[name]('event/one', body, 'access') : await eventsApi[name]('event/one', 'access');
    expect(result).toEqual({ id: 'result' });
    expect(fetchMock).toHaveBeenCalledWith(`http://localhost:8000/api/v1${path}`, {
      method, body: hasBody ? JSON.stringify(body) : undefined,
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer access' },
    });
  });
});
