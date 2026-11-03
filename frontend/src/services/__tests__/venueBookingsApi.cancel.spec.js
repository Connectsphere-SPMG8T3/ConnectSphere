import { afterEach, describe, expect, it, vi } from "vitest";

import { venueBookingsApi } from "@/services/api";

describe("venueBookingsApi.cancel (SCRUM-85)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an authenticated cancel, with no body, for the encoded booking id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200, ok: true, json: async () => ({ id: "b/1", status: "cancelled" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(venueBookingsApi.cancel("b/1", "token")).resolves.toEqual({ id: "b/1", status: "cancelled" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/venue-bookings/b%2F1/cancel");
    expect(init).toMatchObject({ method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }) });
    expect(init.body).toBeUndefined();
  });
});
