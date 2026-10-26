import { createApp, h, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { authStore } = vi.hoisted(() => ({
  authStore: { isAuthenticated: false, role: null },
}));

vi.mock("@/stores/auth", () => ({ useAuthStore: () => authStore }));
vi.mock("@/components/common/Nav.vue", () => ({
  default: { template: '<aside data-testid="app-sidebar">Attendee navigation</aside>' },
}));
vi.mock("@/components/common/TopBar.vue", () => ({
  default: { template: '<header data-testid="app-topbar">Top bar</header>' },
}));
vi.mock("@/components/common/Toast.vue", () => ({
  default: { template: '<div data-testid="app-toast"></div>' },
}));

import App from "@/App.vue";

const mountedApps = [];

async function mountApp(path, meta) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: path.replace(/:[^/]+/g, "event-1"),
      name: "current",
      meta,
      component: { render: () => h("div", "Event page") },
    }],
  });
  await router.push(path.replace(/:[^/]+/g, "event-1"));
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(App).use(router);
  app.mount(el);
  mountedApps.push(app);
  await nextTick();
  return el;
}

describe("App attendee event navigation shell", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    authStore.isAuthenticated = false;
    authStore.role = null;
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("shows the sidebar on the protected My events detail page", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";

    const el = await mountApp("/dashboard/attendee/events/:id", {
      requiresAuth: true,
      allowedRoles: ["attendee"],
    });

    expect(el.querySelector('[data-testid="app-sidebar"]')).toBeTruthy();
    expect(el.querySelector('[data-testid="app-topbar"]')).toBeTruthy();
  });

  it("shows the sidebar on public Explore details only for the active Attendee", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "attendee";

    const el = await mountApp("/attendee/events/:id", {
      requiresAuth: false,
      attendeeNavigation: true,
    });

    expect(el.querySelector('[data-testid="app-sidebar"]')).toBeTruthy();
    expect(el.querySelector('[data-testid="app-topbar"]')).toBeTruthy();
  });

  it("keeps public event details available without showing an attendee sidebar to other roles", async () => {
    authStore.isAuthenticated = true;
    authStore.role = "event_organiser";

    const el = await mountApp("/attendee/events/:id", {
      requiresAuth: false,
      attendeeNavigation: true,
    });

    expect(el.querySelector('[data-testid="app-sidebar"]')).toBeNull();
    expect(el.querySelector('[data-testid="app-topbar"]')).toBeNull();
  });
});
