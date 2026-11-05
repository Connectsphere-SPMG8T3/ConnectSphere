import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn() },
}));

const SIGN_IN_SECRET = "Cs" + "1234";
const SESSION = {
  access_token: "access",
  refresh_token: "refresh",
  profile: { id: "u1", role: "attendee", roles: ["attendee"] },
};

const mountedApps = [];

async function settle() {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
  }
}

async function mountAt(path) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const { default: router } = await import("@/router");
  await router.push(path);
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(RouterView) }).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await settle();
  return { el, router };
}

function fill(el, type, value) {
  const input = el.querySelector(`input[type="${type}"]`);
  input.value = value;
  input.dispatchEvent(new Event("input"));
}

async function submit(el) {
  el.querySelector("form").dispatchEvent(new Event("submit"));
  await settle();
}

describe("LoginView", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("asks for both fields without calling the server", async () => {
    const { el } = await mountAt("/login");

    await submit(el);

    expect(el.textContent).toContain("Email is required.");
    expect(el.textContent).toContain("Password is required.");
    expect(authApi.login).not.toHaveBeenCalled();
  });

  it("asks only for the field still missing", async () => {
    const { el } = await mountAt("/login");
    fill(el, "email", "attendee@connectsphere.dev");

    await submit(el);

    expect(el.textContent).not.toContain("Email is required.");
    expect(el.textContent).toContain("Password is required.");
  });

  it("signs in and goes to the role's dashboard", async () => {
    authApi.login.mockResolvedValue(SESSION);
    const { el, router } = await mountAt("/login");
    fill(el, "email", "attendee@connectsphere.dev");
    fill(el, "password", SIGN_IN_SECRET);

    await submit(el);

    expect(authApi.login).toHaveBeenCalledWith("attendee@connectsphere.dev", SIGN_IN_SECRET);
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/dashboard/attendee"));
  });

  it("returns to the page that asked for a sign-in", async () => {
    authApi.login.mockResolvedValue(SESSION);
    const { el, router } = await mountAt("/login?redirect=/profile/me");
    fill(el, "email", "attendee@connectsphere.dev");
    fill(el, "password", SIGN_IN_SECRET);

    await submit(el);

    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/profile/me"));
  });

  it("stays on the page and shows why a sign-in failed", async () => {
    authApi.login.mockRejectedValue(new ApiError("Invalid email or password.", 401));
    const { el, router } = await mountAt("/login");
    fill(el, "email", "attendee@connectsphere.dev");
    fill(el, "password", "wrong");

    await submit(el);

    expect(el.querySelector('[role="alert"]').textContent).toContain("Invalid email or password.");
    expect(router.currentRoute.value.path).toBe("/login");
  });
});
