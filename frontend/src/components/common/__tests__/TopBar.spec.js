import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn() },
  venuesApi: { search: vi.fn(), get: vi.fn() },
  notificationsApi: {
    unreadCount: vi.fn().mockResolvedValue({ count: 0, latest_at: null }),
    list: vi.fn().mockResolvedValue({ items: [], next_before: null }),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

// Mirrors Nav.spec.js: a fresh router and store module per test so one test's
// in-flight navigation can't leak into the next.
async function mountTopBar(profile) {
  vi.resetModules();
  const pinia = createPinia();
  setActivePinia(pinia);
  const { useAuthStore } = await import("@/stores/auth");
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = profile;
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/dashboard/coordinator");
  const { default: TopBar } = await import("@/components/common/TopBar.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(TopBar).use(pinia).use(router).mount(el);
  await nextTick();
  return { el, router };
}

describe("TopBar", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("greets the user by first name and shows today's date", async () => {
    const { el } = await mountTopBar({ id: "c1", role: "event_coordinator", full_name: "Jack Tan" });
    expect(el.textContent).toContain("Hello Jack");
    expect(el.textContent).not.toContain("Jack Tan");
    const { formatFriendlyDate } = await import("@/components/common/dateFormat");
    expect(el.textContent).toContain(formatFriendlyDate(new Date()));
  });

  it("offers search only to the roles allowed on the venue catalogue", async () => {
    const coordinator = await mountTopBar({ id: "c1", role: "event_coordinator", full_name: "Jack Tan" });
    expect(coordinator.el.querySelector('[role="search"]')).not.toBeNull();

    document.body.innerHTML = "";
    const attendee = await mountTopBar({ id: "a1", role: "attendee", full_name: "Mia Chen" });
    expect(attendee.el.querySelector('[role="search"]')).toBeNull();
  });

  it("shows the notification bell and opens its panel", async () => {
    const { el } = await mountTopBar({ id: "c1", role: "event_coordinator", full_name: "Jack Tan" });
    const bell = el.querySelector('[aria-label="Notifications"]');
    expect(el.textContent).not.toContain("No notifications");

    bell.click();
    await vi.waitFor(() => expect(el.textContent).toContain("No notifications"));
    expect(bell.getAttribute("aria-expanded")).toBe("true");

    bell.click();
    await nextTick();
    expect(el.textContent).not.toContain("No notifications");
  });

  it("gives every role the bell, attendees included", async () => {
    const { el } = await mountTopBar({ id: "a1", role: "attendee", full_name: "Mia Chen" });

    expect(el.querySelector('[aria-label="Notifications"]')).not.toBeNull();
  });
});
