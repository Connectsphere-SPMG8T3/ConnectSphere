import { afterEach, describe, expect, it, vi } from "vitest";

import { venuesApi } from "@/services/api";

describe("venuesApi.calendar (SCRUM-57)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("gets the encoded venue's calendar for a period, authenticated", async () => {
    const body = { venue: { id: "venue/1" }, entries: [] };
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => body });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      venuesApi.calendar(
        "venue/1",
        { startsAt: new Date("2031-03-09T16:00:00Z"), endsAt: new Date("2031-03-16T16:00:00Z") },
        "token",
      ),
    ).resolves.toEqual(body);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "http://localhost:8000/api/v1/venues/venue%2F1/calendar" +
        "?starts_at=2031-03-09T16%3A00%3A00.000Z&ends_at=2031-03-16T16%3A00%3A00.000Z",
    );
    expect(init).toMatchObject({ headers: expect.objectContaining({ Authorization: "Bearer token" }) });
  });
});
