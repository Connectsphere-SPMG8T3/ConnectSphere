import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useEventCommentsStore } from "@/features/events/eventCommentsStore";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { listComments: vi.fn(), addComment: vi.fn() },
}));

const FIRST = { id: "c1", body: "First", created_at: "2026-10-02T03:00:00Z", author: { id: "o1", full_name: "Olivia Tan", role: "event_organiser" } };
const SECOND = { id: "c2", body: "Second", created_at: "2026-10-02T04:00:00Z", author: { id: "m1", full_name: "Marcus Lim", role: "event_coordinator" } };

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

describe("useEventCommentsStore (SCRUM-61)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    const auth = useAuthStore();
    auth.token = "access";
    auth.profile = { id: "o1", role: "event_organiser", full_name: "Olivia Tan" };
  });

  it("loads the thread for an event", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    const store = useEventCommentsStore();

    await store.load("event-1");

    expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access");
    expect(store.comments).toEqual([FIRST]);
    expect(store.error).toBeNull();
    expect(store.isLoading).toBe(false);
  });

  it("clears the previous event's thread before loading another", async () => {
    eventsApi.listComments.mockResolvedValueOnce({ comments: [FIRST] });
    const store = useEventCommentsStore();
    await store.load("event-1");
    const pending = deferred();
    eventsApi.listComments.mockReturnValueOnce(pending.promise);

    const loading = store.load("event-2");

    expect(store.comments).toEqual([]);
    pending.resolve({ comments: [SECOND] });
    await loading;
    expect(store.comments).toEqual([SECOND]);
  });

  it("drops a response for an event that is no longer current", async () => {
    const slow = deferred();
    eventsApi.listComments.mockReturnValueOnce(slow.promise).mockResolvedValueOnce({ comments: [SECOND] });
    const store = useEventCommentsStore();

    const first = store.load("event-1");
    await store.load("event-2");
    slow.resolve({ comments: [FIRST] });
    await first;

    expect(store.eventId).toBe("event-2");
    expect(store.comments).toEqual([SECOND]);
  });

  it("reports a load failure", async () => {
    eventsApi.listComments.mockRejectedValue(new Error("Network down"));
    const store = useEventCommentsStore();

    await store.load("event-1");

    expect(store.comments).toEqual([]);
    expect(store.error).toBe("Network down");
  });

  it("posts the trimmed text and appends the saved comment", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    eventsApi.addComment.mockResolvedValue(SECOND);
    const store = useEventCommentsStore();
    await store.load("event-1");

    const ok = await store.post("  Second  ");

    expect(ok).toBe(true);
    expect(eventsApi.addComment).toHaveBeenCalledWith("event-1", "Second", "access");
    expect(store.comments).toEqual([FIRST, SECOND]);
    expect(store.isPosting).toBe(false);
  });

  it("keeps the thread and reports the error when posting fails", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [FIRST] });
    eventsApi.addComment.mockRejectedValue(new Error("Comments are closed for a rejected event."));
    const store = useEventCommentsStore();
    await store.load("event-1");

    const ok = await store.post("Late question");

    expect(ok).toBe(false);
    expect(store.comments).toEqual([FIRST]);
    expect(store.error).toBe("Comments are closed for a rejected event.");
    expect(store.isPosting).toBe(false);
  });

  it("lets the next event post when a post on the previous event is still in flight", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [] });
    const slowPost = deferred();
    eventsApi.addComment.mockReturnValueOnce(slowPost.promise);
    const store = useEventCommentsStore();
    await store.load("event-1");

    const posting = store.post("On event one");
    await store.load("event-2");
    slowPost.resolve(FIRST);
    await posting;

    expect(store.eventId).toBe("event-2");
    expect(store.isPosting).toBe(false);
    expect(store.comments).toEqual([]);
  });

  it("does not post an invalid comment", async () => {
    const store = useEventCommentsStore();
    store.eventId = "event-1";

    expect(await store.post("   ")).toBe(false);
    expect(eventsApi.addComment).not.toHaveBeenCalled();
  });
});
