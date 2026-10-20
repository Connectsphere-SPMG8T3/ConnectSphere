import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationBell from "@/components/common/NotificationBell.vue";
import { useNotificationsStore } from "@/features/notifications/notificationsStore";
import { notificationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { refresh: vi.fn() },
  notificationsApi: { unreadCount: vi.fn(), list: vi.fn(), markRead: vi.fn(), markAllRead: vi.fn() },
}));

// The poller is exercised in polling.spec.js; here it only has to start and stop.
vi.mock("@/features/notifications/polling", () => ({
  POLL_INTERVAL_MS: 10_000,
  createPoller: vi.fn(() => ({ start: vi.fn(), stop: vi.fn() })),
}));

const UNREAD = { id: "n1", event_id: "e1", type: "event_assigned", message: "You were assigned Partner Summit", link: "/coordinator/events/e1", read: false, created_at: new Date(Date.now() - 5 * 60_000).toISOString() };
const READ = { id: "n2", event_id: "e2", type: "event_approved", message: "Workshop was approved", link: null, read: true, created_at: new Date(Date.now() - 3 * 3_600_000).toISOString() };

async function mountBell({ count = 1, items = [UNREAD, READ] } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "u1", role: "event_coordinator", full_name: "Jack Tan" };
  notificationsApi.unreadCount.mockResolvedValue({ count, latest_at: "t1" });
  notificationsApi.list.mockResolvedValue({ items, next_before: null });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/coordinator/events/:id", component: { template: "<div />" } },
      { path: "/other", component: { template: "<div />" } },
    ],
  });
  await router.push("/");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(NotificationBell).use(pinia).use(router);
  app.mount(el);
  const store = useNotificationsStore();
  await store.poll();
  await nextTick();
  return { el, router, store, app };
}

const bellButton = (el) => el.querySelector('button[aria-label^="Notifications"]');

describe("NotificationBell (113)", () => {
  let mounted;

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });
  afterEach(() => {
    mounted?.app.unmount();
    mounted = null;
  });

  it("shows the unread count on the bell", async () => {
    mounted = await mountBell({ count: 3 });

    expect(mounted.el.textContent).toContain("3");
    expect(bellButton(mounted.el).getAttribute("aria-label")).toContain("3 unread");
  });

  it("shows no badge when nothing is unread", async () => {
    mounted = await mountBell({ count: 0 });

    expect(mounted.el.querySelector('[data-testid="notification-badge"]')).toBeNull();
    expect(bellButton(mounted.el).getAttribute("aria-label")).toBe("Notifications");
  });

  it("caps the badge at 99+", async () => {
    mounted = await mountBell({ count: 250 });

    expect(mounted.el.querySelector('[data-testid="notification-badge"]').textContent.trim()).toBe("99+");
  });

  it("starts polling when it appears and stops when it goes", async () => {
    mounted = await mountBell();
    const { createPoller } = await import("@/features/notifications/polling");
    const poller = createPoller.mock.results[0].value;

    expect(poller.start).toHaveBeenCalledTimes(1);
    mounted.app.unmount();
    expect(poller.stop).toHaveBeenCalledTimes(1);
    mounted = null;
  });

  it("opening the panel lists notifications newest first, with a time and an unread mark", async () => {
    mounted = await mountBell();

    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.textContent).toContain("You were assigned Partner Summit"));

    const rows = [...mounted.el.querySelectorAll("li")];
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("You were assigned Partner Summit");
    expect(rows[0].textContent).toContain("5 min ago");
    expect(rows[0].getAttribute("aria-label")).toContain("unread");
    expect(rows[1].getAttribute("aria-label") ?? "").not.toContain("unread");
    expect(bellButton(mounted.el).getAttribute("aria-expanded")).toBe("true");
  });

  it("an item with a link is a link; an item without one is plain text", async () => {
    mounted = await mountBell();

    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(2));

    const rows = mounted.el.querySelectorAll("li");
    expect(rows[0].querySelector("a").getAttribute("href")).toBe("/coordinator/events/e1");
    expect(rows[1].querySelector("a")).toBeNull();
  });

  it("clicking an item marks it read, closes the panel and goes to its page", async () => {
    notificationsApi.markRead.mockResolvedValue({ id: "n1", read: true });
    mounted = await mountBell({ count: 1 });
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(2));

    mounted.el.querySelector("li a").click();
    await vi.waitFor(() => expect(mounted.router.currentRoute.value.path).toBe("/coordinator/events/e1"));

    expect(notificationsApi.markRead).toHaveBeenCalledWith("n1", "access");
    expect(mounted.store.isOpen).toBe(false);
  });

  it("mark all as read clears the unread marks and the badge", async () => {
    notificationsApi.markAllRead.mockResolvedValue({ updated: 1 });
    mounted = await mountBell({ count: 1 });
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(2));

    [...mounted.el.querySelectorAll("button")].find((b) => /mark all as read/i.test(b.textContent)).click();
    await vi.waitFor(() => expect(mounted.store.count).toBe(0));
    await nextTick();

    expect(mounted.el.querySelector('[data-testid="notification-badge"]')).toBeNull();
  });

  it("hides mark all as read when nothing is unread", async () => {
    mounted = await mountBell({ count: 0, items: [READ] });
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(1));

    expect([...mounted.el.querySelectorAll("button")].some((b) => /mark all as read/i.test(b.textContent))).toBe(false);
  });

  it("shows the empty state", async () => {
    mounted = await mountBell({ count: 0, items: [] });

    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.textContent).toContain("No notifications"));
  });

  it("shows an error when the list cannot be loaded", async () => {
    mounted = await mountBell({ count: 0, items: [] });
    notificationsApi.list.mockRejectedValue(new Error("Server error"));

    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.textContent).toContain("Server error"));
  });

  it("offers older notifications when there are more, and loads them", async () => {
    mounted = await mountBell();
    notificationsApi.list.mockResolvedValueOnce({ items: [UNREAD], next_before: "cur" });
    notificationsApi.list.mockResolvedValueOnce({ items: [READ], next_before: null });
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(1));

    [...mounted.el.querySelectorAll("button")].find((b) => /older/i.test(b.textContent)).click();
    await vi.waitFor(() => expect(mounted.el.querySelectorAll("li")).toHaveLength(2));

    expect(notificationsApi.list).toHaveBeenLastCalledWith({ limit: 20, before: "cur" }, "access");
  });

  it("closes on click-away", async () => {
    mounted = await mountBell();
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.store.isOpen).toBe(true));

    mounted.el.querySelector('[data-testid="notification-scrim"]').click();
    await nextTick();

    expect(mounted.store.isOpen).toBe(false);
  });

  it("closes when the route changes", async () => {
    mounted = await mountBell();
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.store.isOpen).toBe(true));

    await mounted.router.push("/other");
    await nextTick();

    expect(mounted.store.isOpen).toBe(false);
  });

  it("the bell toggles the panel", async () => {
    mounted = await mountBell();
    bellButton(mounted.el).click();
    await vi.waitFor(() => expect(mounted.store.isOpen).toBe(true));

    bellButton(mounted.el).click();
    await nextTick();

    expect(mounted.store.isOpen).toBe(false);
  });
});
