import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn() },
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

  it("has no search box", async () => {
    const { el } = await mountTopBar({ id: "c1", role: "event_coordinator", full_name: "Jack Tan" });
    expect(el.querySelector('[role="search"]')).toBeNull();
  });

  it("shows the Acting as switcher on wider screens for an account with several roles", async () => {
    const { el } = await mountTopBar({
      id: "u1", role: "event_coordinator", roles: ["event_coordinator", "venue_staff"], full_name: "Multi Role",
    });
    const switcher = el.querySelector('[data-testid="role-switcher"]');
    expect(switcher.textContent).toContain("Role:");
    const select = switcher.querySelector("select");
    expect(select.getAttribute("aria-label")).toBe("Acting as role");
    expect(select.value).toBe("event_coordinator");
    expect([...select.options].map((option) => option.textContent.trim())).toEqual(["Event Coordinator", "Venue Staff"]);
  });

  it("sizes the switcher like the bell: one 40px box with a hard shadow", async () => {
    const { el } = await mountTopBar({
      id: "u1", role: "event_coordinator", roles: ["event_coordinator", "venue_staff"], full_name: "Multi Role",
    });
    const box = el.querySelector('[data-testid="role-switcher"] label');
    // Yellow like the current page's sidebar link, since it shows the current role.
    for (const name of ["h-10", "border-2", "border-ink", "shadow-hard", "bg-bauhaus-yellow", "hover:bg-muted"]) {
      expect(box.classList.contains(name)).toBe(true);
    }
    // A mouse click focuses the select too; the ring is for keyboard focus only.
    expect([...box.classList].some((name) => name.startsWith("focus-within:"))).toBe(false);
    expect(box.classList.contains("has-[:focus-visible]:outline")).toBe(true);
  });

  it("switches role from the top bar and opens that role's dashboard", async () => {
    const { el, router } = await mountTopBar({
      id: "u1", role: "event_coordinator", roles: ["event_coordinator", "venue_staff"], full_name: "Multi Role",
    });
    const { authApi } = await import("@/services/api");
    authApi.setActiveRole.mockResolvedValue({
      id: "u1", role: "venue_staff", roles: ["event_coordinator", "venue_staff"], full_name: "Multi Role",
    });
    const select = el.querySelector('[data-testid="role-switcher"] select');
    select.value = "venue_staff";
    select.dispatchEvent(new Event("change"));
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/dashboard/venue-staff"));
  });

  it("shows no switcher for a single-role account, or on a phone where the menu holds it", async () => {
    const single = await mountTopBar({ id: "c1", role: "event_coordinator", full_name: "Jack Tan" });
    expect(single.el.querySelector('[data-testid="role-switcher"]')).toBeNull();

    document.body.innerHTML = "";
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
    const phone = await mountTopBar({
      id: "u1", role: "event_coordinator", roles: ["event_coordinator", "venue_staff"], full_name: "Multi Role",
    });
    expect(phone.el.querySelector('[data-testid="role-switcher"]')).toBeNull();
    delete window.matchMedia;
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
