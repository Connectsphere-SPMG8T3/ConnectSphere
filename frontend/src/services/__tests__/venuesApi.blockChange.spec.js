import { afterEach, describe, expect, it, vi } from "vitest";

import { venuesApi } from "@/services/api";

describe("venuesApi.changeBlock (SCRUM-54)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an authenticated change for the encoded venue and block ids", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200, ok: true, json: async () => ({ block: { id: "blk/1" }, restorable: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const payload = { action: "remove", ends_at: null, note: null };

    await expect(venuesApi.changeBlock("venue/1", "blk/1", payload, "token"))
      .resolves.toEqual({ block: { id: "blk/1" }, restorable: [] });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/venues/venue%2F1/blocks/blk%2F1/change");
    expect(init).toMatchObject({ method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token" }) });
    expect(JSON.parse(init.body)).toEqual(payload);
  });
});
