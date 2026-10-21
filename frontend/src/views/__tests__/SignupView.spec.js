import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { RouterView } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn(), setActiveRole: vi.fn(), signup: vi.fn() },
}));

const CREATED_PROFILE = {
  id: "new-organiser",
  email: "olivia@connectsphere.dev",
  full_name: "Olivia Organiser",
  role: "event_organiser",
  organisation_name: "SMU Events Club",
  department: null,
  phone_number: "+65 9123 4567",
  roles: ["event_organiser"],
};

const CREATED_ATTENDEE_PROFILE = {
  id: "new-attendee",
  email: "avery@connectsphere.dev",
  full_name: "Avery Attendee",
  role: "attendee",
  organisation_name: null,
  department: null,
  phone_number: null,
  roles: ["attendee"],
};

const mountedApps = [];

// Several ticks: navigation resolves a lazily imported view before it renders.
async function settle() {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await nextTick();
  }
}

// Mounts the whole app at `path`, so navigating away from sign-up renders the next view.
async function mountAt(path, { signedInAs } = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  if (signedInAs) {
    const authStore = useAuthStore();
    authStore.token = "access";
    authStore.refreshToken = "refresh";
    authStore.profile = signedInAs;
    authStore.sessionVerified = true;
  }
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

function field(el, label) {
  const labelEl = [...el.querySelectorAll("label")].find((node) => node.textContent.replace("*", "").trim() === label);
  if (!labelEl) throw new Error(`No field labelled "${label}"`);
  return el.querySelector(`#${labelEl.htmlFor}`);
}

// The message BauhausInput shows under the field, or "" if there is none.
function errorFor(el, label) {
  const input = field(el, label);
  return el.querySelector(`#${input.id}-error`)?.textContent.trim() ?? "";
}

function fill(el, label, value) {
  const input = field(el, label);
  input.value = value;
  input.dispatchEvent(new Event("input"));
}

function fillValidForm(el) {
  fill(el, "Full name", "Olivia Organiser");
  fill(el, "Email", "olivia@connectsphere.dev");
  fill(el, "Password", "Secure123");
  fill(el, "Organisation name", "SMU Events Club");
  fill(el, "Phone number", "+65 9123 4567");
}

async function submit(el) {
  el.querySelector("form").dispatchEvent(new Event("submit"));
  await settle();
}

describe("SignupView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  it("signs up an organiser and lands on login with a confirmation and the email filled in", async () => {
    authApi.signup.mockResolvedValue(CREATED_PROFILE);
    const { el, router } = await mountAt("/signup");

    fillValidForm(el);
    await submit(el);

    expect(authApi.signup).toHaveBeenCalledWith({
      role: "event_organiser",
      full_name: "Olivia Organiser",
      email: "olivia@connectsphere.dev",
      password: "Secure123",
      organisation_name: "SMU Events Club",
      phone_number: "+65 9123 4567",
    });
    // The first visit to login lazily loads and compiles that view.
    await vi.waitFor(() => expect(el.textContent).toContain("Account created. Please sign in."));
    expect(router.currentRoute.value.name).toBe("login");
    expect(field(el, "Email").value).toBe("olivia@connectsphere.dev");
  });

  it("signs up an attendee on the attendee-specific page without organiser fields", async () => {
    authApi.signup.mockResolvedValue(CREATED_ATTENDEE_PROFILE);
    const { el, router } = await mountAt("/signup/attendee");

    expect(el.textContent).toContain("Create an Attendee Account");
    expect(() => field(el, "Account Type")).toThrow();
    expect(() => field(el, "Organisation name")).toThrow();
    expect(() => field(el, "Phone number")).toThrow();
    fill(el, "Full name", "Avery Attendee");
    fill(el, "Email", "avery@connectsphere.dev");
    fill(el, "Password", "Secure123");
    await submit(el);

    expect(authApi.signup).toHaveBeenCalledWith({
      role: "attendee",
      full_name: "Avery Attendee",
      email: "avery@connectsphere.dev",
      password: "Secure123",
    });
    await vi.waitFor(() => expect(el.textContent).toContain("Account created. Please sign in."));
    expect(router.currentRoute.value.name).toBe("login");
    expect(field(el, "Email").value).toBe("avery@connectsphere.dev");
  });

  it("shows the attendee's missing required fields without requiring organiser fields", async () => {
    const { el } = await mountAt("/signup/attendee");

    await submit(el);

    expect(errorFor(el, "Full name")).toBe("Full name is required.");
    expect(errorFor(el, "Email")).toBe("Email is required.");
    expect(errorFor(el, "Password")).toBe("Password is required.");
    expect(() => field(el, "Organisation name")).toThrow();
    expect(() => field(el, "Phone number")).toThrow();
    expect(authApi.signup).not.toHaveBeenCalled();
  });

  it("shows which required fields are empty and does not submit", async () => {
    const { el } = await mountAt("/signup");

    fill(el, "Full name", "   ");
    await submit(el);

    expect(errorFor(el, "Full name")).toBe("Full name is required.");
    expect(errorFor(el, "Email")).toBe("Email is required.");
    expect(errorFor(el, "Password")).toBe("Password is required.");
    expect(errorFor(el, "Organisation name")).toBe("Organisation name is required.");
    expect(errorFor(el, "Phone number")).toBe("");
    expect(authApi.signup).not.toHaveBeenCalled();
  });

  it.each(["not-an-email", "olivia@", "@connectsphere.dev", "olivia connectsphere.dev"])(
    "rejects the invalid email %j before submitting",
    async (email) => {
      const { el } = await mountAt("/signup");

      fillValidForm(el);
      fill(el, "Email", email);
      await submit(el);

      expect(errorFor(el, "Email")).toBe("Enter a valid email address.");
      expect(authApi.signup).not.toHaveBeenCalled();
    },
  );

  // Built from their parts: password-like literals trip GitGuardian. The
  // superscript case matches the backend, which counts only decimal digits.
  it.each(["a".repeat(6) + "1", "a".repeat(8), "1".repeat(8), "a".repeat(7) + "\u00b2"])(
    "rejects the password %j, explaining the rule, before submitting",
    async (password) => {
      const { el } = await mountAt("/signup");

      fillValidForm(el);
      fill(el, "Password", password);
      await submit(el);

      expect(errorFor(el, "Password")).toBe(
        "Password must be at least 8 characters and include at least one letter and one digit.",
      );
      expect(authApi.signup).not.toHaveBeenCalled();
    },
  );

  it("shows an already-registered email under the email field and stays on the form", async () => {
    authApi.signup.mockRejectedValue(new ApiError("An account with this email already exists.", 409));
    const { el, router } = await mountAt("/signup");

    fillValidForm(el);
    await submit(el);

    expect(errorFor(el, "Email")).toBe("An account with this email already exists.");
    expect(router.currentRoute.value.name).toBe("signup");
  });

  it("shows each field error the server returns under the field it names", async () => {
    authApi.signup.mockRejectedValue(
      new ApiError("Password rule, Organisation rule", 422, [
        {
          loc: ["body", "password"],
          msg: "Password must be at least 8 characters and include at least one letter and one digit.",
        },
        { loc: ["body", "organisation_name"], msg: "String should have at least 1 character" },
      ]),
    );
    const { el, router } = await mountAt("/signup");

    fillValidForm(el);
    await submit(el);

    expect(errorFor(el, "Password")).toBe(
      "Password must be at least 8 characters and include at least one letter and one digit.",
    );
    expect(errorFor(el, "Organisation name")).toBe("String should have at least 1 character");
    expect(errorFor(el, "Email")).toBe("");
    expect(router.currentRoute.value.name).toBe("signup");
  });

  it.each([
    [
      "the service is unavailable",
      new ApiError("The authentication service is temporarily unavailable. Please try again.", 503),
      "The authentication service is temporarily unavailable. Please try again.",
    ],
    ["the network fails", new TypeError("Failed to fetch"), "Could not create your account. Please try again."],
  ])("when %s, shows a general error and keeps what was entered", async (_case, failure, message) => {
    authApi.signup.mockRejectedValue(failure);
    const { el, router } = await mountAt("/signup");

    fillValidForm(el);
    await submit(el);

    expect(el.querySelector('[role="alert"]')?.textContent.trim()).toBe(message);
    expect(field(el, "Full name").value).toBe("Olivia Organiser");
    expect(field(el, "Email").value).toBe("olivia@connectsphere.dev");
    expect(field(el, "Organisation name").value).toBe("SMU Events Club");
    expect(router.currentRoute.value.name).toBe("signup");
  });

  it("signs up without a phone number when it is left empty", async () => {
    authApi.signup.mockResolvedValue({ ...CREATED_PROFILE, phone_number: null });
    const { el } = await mountAt("/signup");

    fillValidForm(el);
    fill(el, "Phone number", "  ");
    await submit(el);

    expect(authApi.signup).toHaveBeenCalledWith(expect.objectContaining({ phone_number: null }));
  });

  it("is reachable from the login page", async () => {
    const { el, router } = await mountAt("/login");

    el.querySelector('a[href="/signup/organiser"]').dispatchEvent(
      new MouseEvent("click", { bubbles: true, button: 0 }),
    );
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("signup"));
    expect(el.textContent).toContain("Create an Event Organiser Account");
  });

  it("offers separate organiser and attendee signup pages from login", async () => {
    const { el, router } = await mountAt("/login");

    expect([...el.querySelectorAll('a[href^="/signup"]')].map((link) => link.getAttribute("href"))).toEqual([
      "/signup/organiser",
      "/signup/attendee",
    ]);

    el.querySelector('a[href="/signup/attendee"]').dispatchEvent(
      new MouseEvent("click", { bubbles: true, button: 0 }),
    );
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/signup/attendee"));
    expect(el.textContent).toContain("Sign up as an Attendee to use ConnectSphere.");
    expect(() => field(el, "Account Type")).toThrow();
  });

  it("redirects the legacy signup URL to organiser signup", async () => {
    const { router } = await mountAt("/signup");

    expect(router.currentRoute.value.path).toBe("/signup/organiser");
    expect(router.currentRoute.value.name).toBe("signup");
  });

  it("sends someone already signed in to their dashboard instead", async () => {
    const { router } = await mountAt("/signup", { signedInAs: CREATED_PROFILE });

    expect(router.currentRoute.value.path).toBe("/dashboard/organiser");
  });

  it("sends and pre-fills an email typed with surrounding spaces without them", async () => {
    authApi.signup.mockResolvedValue(CREATED_PROFILE);
    const { el } = await mountAt("/signup");

    fillValidForm(el);
    fill(el, "Email", "  olivia@connectsphere.dev  ");
    await submit(el);

    expect(authApi.signup).toHaveBeenCalledWith(expect.objectContaining({ email: "olivia@connectsphere.dev" }));
    await vi.waitFor(() => expect(el.textContent).toContain("Account created. Please sign in."));
    expect(field(el, "Email").value).toBe("olivia@connectsphere.dev");
  });
});
