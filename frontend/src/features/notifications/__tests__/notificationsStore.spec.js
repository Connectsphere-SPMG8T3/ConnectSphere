import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useNotificationsStore } from "@/features/notifications/notificationsStore";
import { ApiError, notificationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { refresh: vi.fn() },
  notificationsApi: { unreadCount: vi.fn(), list: vi.fn(), markRead: vi.fn(), markAllRead: vi.fn() },
}));

const pollers = [];
vi.mock("@/features/notifications/polling", () => ({
  POLL_INTERVAL_MS: 10_000,
  createPoller: vi.fn((options) => {
    const poller = { options, start: vi.fn(), stop: vi.fn() };
    pollers.push(poller);
    return poller;
  }),
}));

const ITEM_1 = { id: "n1", event_id: "e1", type: "event_assigned", message: "First", link: "/coordinator/events/e1", read: false, created_at: "2026-10-20T03:00:00Z" };
const ITEM_2 = { id: "n2", event_id: "e1", type: "event_assigned", message: "Second", link: "/coordinator/events/e1", read: true, created_at: "2026-10-20T02:00:00Z" };

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("useNotificationsStore (113)", () => {
  let auth;

  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    pollers.length = 0;
    auth = useAuthStore();
    auth.token = "access";
    auth.refreshToken = "refresh";
    auth.profile = { id: "u1", role: "event_coordinator", full_name: "Jack Tan" };
  });

  describe("poll", () => {
    it("stores the unread count and the newest time", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 3, latest_at: "2026-10-20T03:00:00Z" });
      const store = useNotificationsStore();

      await store.poll();

      expect(notificationsApi.unreadCount).toHaveBeenCalledWith("access");
      expect(store.count).toBe(3);
      expect(store.latestAt).toBe("2026-10-20T03:00:00Z");
    });

    it("does not fetch the list while the panel is closed", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 1, latest_at: "t1" });
      const store = useNotificationsStore();

      await store.poll();

      expect(notificationsApi.list).not.toHaveBeenCalled();
    });

    it("reloads the open list only when the count or newest time changed", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 1, latest_at: "t1" });
      notificationsApi.list.mockResolvedValue({ items: [ITEM_1], next_before: null });
      const store = useNotificationsStore();
      await store.open();
      notificationsApi.list.mockClear();

      await store.poll();
      expect(notificationsApi.list).toHaveBeenCalledTimes(1); // first poll: 0 -> 1

      await store.poll();
      expect(notificationsApi.list).toHaveBeenCalledTimes(1); // unchanged

      notificationsApi.unreadCount.mockResolvedValue({ count: 1, latest_at: "t2" });
      await store.poll();
      expect(notificationsApi.list).toHaveBeenCalledTimes(2); // newest time moved
    });

    it("skips silently on an outage and keeps the last good count", async () => {
      notificationsApi.unreadCount.mockResolvedValueOnce({ count: 2, latest_at: "t1" });
      const store = useNotificationsStore();
      await store.poll();
      notificationsApi.unreadCount.mockRejectedValue(new ApiError("Server error", 503));

      await expect(store.poll()).resolves.toBeUndefined();

      expect(store.count).toBe(2);
      expect(store.error).toBeNull();
    });

    it("ends the session like every other call when the server rejects it", async () => {
      const { authApi } = await import("@/services/api");
      notificationsApi.unreadCount.mockRejectedValue(new ApiError("Invalid or expired authentication token.", 401));
      authApi.refresh.mockRejectedValue(new ApiError("expired", 401));
      const store = useNotificationsStore();

      await expect(store.poll()).resolves.toBeUndefined();

      expect(auth.token).toBeNull();
    });

    it("does nothing without a session", async () => {
      auth.token = null;
      const store = useNotificationsStore();

      await store.poll();

      expect(notificationsApi.unreadCount).not.toHaveBeenCalled();
    });
  });

  describe("the panel", () => {
    it("opening loads the list and marks nothing read", async () => {
      notificationsApi.list.mockResolvedValue({ items: [ITEM_1, ITEM_2], next_before: "cur" });
      const store = useNotificationsStore();
      store.count = 1;

      await store.open();

      expect(store.isOpen).toBe(true);
      expect(notificationsApi.list).toHaveBeenCalledWith({ limit: 20 }, "access");
      expect(store.items).toEqual([ITEM_1, ITEM_2]);
      expect(store.nextBefore).toBe("cur");
      expect(notificationsApi.markRead).not.toHaveBeenCalled();
      expect(store.count).toBe(1);
    });

    it("a failed load keeps the panel open and shows the error", async () => {
      notificationsApi.list.mockRejectedValue(new ApiError("Server error", 503));
      const store = useNotificationsStore();

      await store.open();

      expect(store.isOpen).toBe(true);
      expect(store.error).toBe("Server error");
      expect(store.isLoading).toBe(false);
    });

    it("closing hides the panel", async () => {
      notificationsApi.list.mockResolvedValue({ items: [], next_before: null });
      const store = useNotificationsStore();
      await store.open();

      store.close();

      expect(store.isOpen).toBe(false);
    });

    it("loadMore appends the next page using the cursor", async () => {
      notificationsApi.list
        .mockResolvedValueOnce({ items: [ITEM_1], next_before: "cur" })
        .mockResolvedValueOnce({ items: [ITEM_2], next_before: null });
      const store = useNotificationsStore();
      await store.open();

      await store.loadMore();

      expect(notificationsApi.list).toHaveBeenLastCalledWith({ limit: 20, before: "cur" }, "access");
      expect(store.items).toEqual([ITEM_1, ITEM_2]);
      expect(store.nextBefore).toBeNull();
    });

    it("loadMore does nothing on the last page", async () => {
      notificationsApi.list.mockResolvedValue({ items: [ITEM_1], next_before: null });
      const store = useNotificationsStore();
      await store.open();
      notificationsApi.list.mockClear();

      await store.loadMore();

      expect(notificationsApi.list).not.toHaveBeenCalled();
    });
  });

  describe("marking read", () => {
    async function openWith(items, count) {
      notificationsApi.list.mockResolvedValue({ items: structuredClone(items), next_before: null });
      const store = useNotificationsStore();
      store.count = count;
      await store.open();
      return store;
    }

    it("markRead updates the item and lowers the count without waiting for a poll", async () => {
      notificationsApi.markRead.mockResolvedValue({ id: "n1", read: true });
      const store = await openWith([ITEM_1, ITEM_2], 1);

      await store.markRead("n1");

      expect(notificationsApi.markRead).toHaveBeenCalledWith("n1", "access");
      expect(store.items[0].read).toBe(true);
      expect(store.count).toBe(0);
    });

    it("marking an already-read item leaves the count alone", async () => {
      notificationsApi.markRead.mockResolvedValue({ id: "n2", read: true });
      const store = await openWith([ITEM_1, ITEM_2], 1);

      await store.markRead("n2");

      expect(store.count).toBe(1);
    });

    it("the count never goes below zero", async () => {
      notificationsApi.markRead.mockResolvedValue({ id: "n1", read: true });
      const store = await openWith([ITEM_1], 0);

      await store.markRead("n1");

      expect(store.count).toBe(0);
    });

    it("a failed markRead keeps the item unread and shows the error", async () => {
      notificationsApi.markRead.mockRejectedValue(new ApiError("Notification not found.", 404));
      const store = await openWith([ITEM_1], 1);

      await store.markRead("n1");

      expect(store.items[0].read).toBe(false);
      expect(store.count).toBe(1);
      expect(store.error).toBe("Notification not found.");
    });

    it("markAllRead zeroes the count and marks every loaded item read", async () => {
      notificationsApi.markAllRead.mockResolvedValue({ updated: 1 });
      const store = await openWith([ITEM_1, ITEM_2], 1);

      await store.markAllRead();

      expect(notificationsApi.markAllRead).toHaveBeenCalledWith("access");
      expect(store.items.every((item) => item.read)).toBe(true);
      expect(store.count).toBe(0);
    });

    it("a failed markAllRead leaves everything as it was", async () => {
      notificationsApi.markAllRead.mockRejectedValue(new ApiError("Server error", 503));
      const store = await openWith([ITEM_1], 1);

      await store.markAllRead();

      expect(store.items[0].read).toBe(false);
      expect(store.count).toBe(1);
      expect(store.error).toBe("Server error");
    });
  });

  describe("switching role", () => {
    it("clears the old role's bell and polls the new role at once", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 4, latest_at: "t1" });
      notificationsApi.list.mockResolvedValue({ items: [ITEM_1], next_before: null });
      const store = useNotificationsStore();
      store.start();
      await store.poll();
      await store.open();
      expect(store.count).toBe(4);
      notificationsApi.unreadCount.mockClear();
      notificationsApi.unreadCount.mockResolvedValue({ count: 0, latest_at: null });

      auth.profile = { ...auth.profile, role: "event_organiser" };
      await vi.waitFor(() => expect(notificationsApi.unreadCount).toHaveBeenCalledTimes(1));

      expect(store.items).toEqual([]);
      expect(store.isOpen).toBe(false);
      expect(store.count).toBe(0);
      store.stop();
    });

    it("a token refresh (same role) leaves the bell alone", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 4, latest_at: "t1" });
      const store = useNotificationsStore();
      store.start();
      await store.poll();
      notificationsApi.unreadCount.mockClear();

      auth.token = "renewed-access-token";
      await Promise.resolve();

      expect(store.count).toBe(4);
      expect(notificationsApi.unreadCount).not.toHaveBeenCalled();
      store.stop();
    });

    it("a slow list for the previous role never lands after the switch", async () => {
      const slow = deferred();
      notificationsApi.list.mockReturnValue(slow.promise);
      notificationsApi.unreadCount.mockResolvedValue({ count: 0, latest_at: null });
      const store = useNotificationsStore();
      store.start();
      const opening = store.open();

      auth.profile = { ...auth.profile, role: "event_organiser" };
      slow.resolve({ items: [ITEM_1], next_before: "old" });
      await opening;

      expect(store.items).toEqual([]);
      expect(store.nextBefore).toBeNull();
      store.stop();
    });

    it.each([
      ["markRead succeeds", "markRead", "resolve"],
      ["markRead fails", "markRead", "reject"],
      ["markAllRead succeeds", "markAllRead", "resolve"],
      ["markAllRead fails", "markAllRead", "reject"],
    ])("when %s after the switch it changes nothing on the new role's bell", async (_name, action, outcome) => {
      const slow = deferred();
      notificationsApi[action].mockReturnValue(slow.promise);
      notificationsApi.unreadCount.mockResolvedValue({ count: 2, latest_at: null });
      const store = useNotificationsStore();
      store.start();
      const acting = action === "markRead" ? store.markRead("n1") : store.markAllRead();

      auth.profile = { ...auth.profile, role: "event_organiser" };
      await vi.waitFor(() => expect(store.count).toBe(2)); // the new role's own unread count
      if (outcome === "resolve") slow.resolve({ id: "n1", read: true, updated: 1 });
      else slow.reject(new ApiError("Server error", 503));
      await acting;

      expect(store.count).toBe(2);
      expect(store.error).toBeNull();
      store.stop();
    });

    it("a slow poll for the previous role never lands after the switch", async () => {
      const slow = deferred();
      notificationsApi.unreadCount.mockReturnValueOnce(slow.promise);
      const store = useNotificationsStore();
      store.start();
      const polling = store.poll();

      notificationsApi.unreadCount.mockResolvedValue({ count: 0, latest_at: null });
      auth.profile = { ...auth.profile, role: "event_organiser" };
      slow.resolve({ count: 9, latest_at: "old" });
      await polling;

      expect(store.count).not.toBe(9);
      store.stop();
    });
  });

  describe("start and stop", () => {
    it("start runs the poller, and its tick polls", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 2, latest_at: "t1" });
      const store = useNotificationsStore();

      store.start();

      expect(pollers).toHaveLength(1);
      expect(pollers[0].start).toHaveBeenCalledTimes(1);
      await pollers[0].options.tick();
      expect(store.count).toBe(2);
      store.stop();
    });

    it("starting twice reuses the one poller", () => {
      const store = useNotificationsStore();

      store.start();
      store.start();

      expect(pollers).toHaveLength(1);
      expect(pollers[0].start).toHaveBeenCalledTimes(1);
      store.stop();
    });

    it("stop stops the poller, forgets the role watch and clears the bell", async () => {
      notificationsApi.unreadCount.mockResolvedValue({ count: 2, latest_at: "t1" });
      const store = useNotificationsStore();
      store.start();
      await store.poll();

      store.stop();

      expect(pollers[0].stop).toHaveBeenCalledTimes(1);
      expect(store.count).toBe(0);
      notificationsApi.unreadCount.mockClear();
      auth.profile = { ...auth.profile, role: "event_organiser" };
      await Promise.resolve();
      expect(notificationsApi.unreadCount).not.toHaveBeenCalled();
    });

    it("stop without start is harmless", () => {
      const store = useNotificationsStore();

      expect(() => store.stop()).not.toThrow();
    });
  });
});
