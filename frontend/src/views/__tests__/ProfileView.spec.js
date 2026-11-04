import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: {
    login: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    setActiveRole: vi.fn(),
    updateProfile: vi.fn(),
  },
}));

async function mountProfileView(profile) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = profile;
  authStore.sessionVerified = true;
  const { default: router } = await import("@/router");
  await router.push("/profile/me");
  const { default: ProfileView } = await import("@/views/ProfileView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(ProfileView).use(pinia).use(router);
  app.mount(el);
  await nextTick();
  await nextTick();
  return { el, authStore };
}

function field(el, label) {
  const labelElement = [...el.querySelectorAll("label")].find(
    (node) => node.textContent.replace("*", "").trim() === label,
  );
  if (!labelElement) throw new Error(`No field labelled "${label}"`);
  return el.querySelector(`#${labelElement.htmlFor}`);
}

function fill(el, label, value) {
  const input = field(el, label);
  input.value = value;
  input.dispatchEvent(new Event("input"));
}

async function submit(el) {
  el.querySelector("form").dispatchEvent(new Event("submit"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
  await nextTick();
}

describe("ProfileView", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("does not show an all-roles list for a single-role account", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });

    expect(el.textContent).not.toContain("All roles");
  });

  it("lists every held role with human-readable labels for a multi-role account", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Marcus Lim",
      email: "coordinator@connectsphere.dev",
      role: "venue_staff",
      roles: ["event_coordinator", "venue_staff"],
    });

    expect(el.textContent).toContain("All roles");
    expect(el.textContent).toContain("Event Coordinator");
    expect(el.textContent).toContain("Venue Staff");
  });

  it("leaves an unrecognized existing phone value unchanged in the profile display", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
      phone_number: "legacy phone value",
    });

    expect(el.textContent).toContain("legacy phone value");
  });

  it("saves the edited name and optional phone and displays the saved profile", async () => {
    const profile = {
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
      phone_number: "+65 9000 0000",
    };
    const updatedProfile = { ...profile, full_name: "Siti Updated", phone_number: "+6591234567" };
    const { el, authStore } = await mountProfileView(profile);
    authApi.updateProfile.mockResolvedValue(updatedProfile);

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Full name", "Siti Updated");
    fill(el, "Phone number", "9123-4567");
    await submit(el);

    expect(authApi.updateProfile).toHaveBeenCalledWith("access", {
      full_name: "Siti Updated",
      phone_number: "+6591234567",
    });
    expect(authStore.profile).toEqual(updatedProfile);
    expect(el.textContent).toContain("Siti Updated");
    expect(el.textContent).toContain("+65 91234567");
    expect(el.textContent).not.toContain("+65 9000 0000");
  });

  it("shows a field error and does not send a whitespace-only name", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Full name", "   ");
    await submit(el);

    const nameInput = field(el, "Full name");
    expect(el.querySelector(`#${nameInput.id}-error`)?.textContent.trim()).toBe("Full name is required.");
    expect(authApi.updateProfile).not.toHaveBeenCalled();
  });

  it("rejects a phone number shorter than eight digits before calling the API", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Phone number", "1234567");
    await submit(el);

    const phoneInput = field(el, "Phone number");
    expect(el.querySelector(`#${phoneInput.id}-error`)?.textContent.trim()).toBe(
      "Enter 8 digits, with an optional +65 country code.",
    );
    expect(authApi.updateProfile).not.toHaveBeenCalled();
  });

  it("cancels edits and discards validation errors", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
      phone_number: "+65 9000 0000",
    });

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Full name", "   ");
    await submit(el);
    expect(el.textContent).toContain("Full name is required.");

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Cancel").click();
    await nextTick();
    expect(el.querySelector("form")).toBeNull();
    expect(el.textContent).not.toContain("Full name is required.");
    expect(el.textContent).toContain("Siti Rahman");

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    expect(field(el, "Full name").value).toBe("Siti Rahman");
    expect(field(el, "Phone number").value).toBe("+65 90000000");
  });

  it("shows server validation errors beside their matching fields", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });
    authApi.updateProfile.mockRejectedValue(
      new ApiError("Phone number is invalid.", 422, [
        { loc: ["body", "phone_number"], msg: "Phone number is invalid." },
      ]),
    );

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Full name", "Siti Rahman");
    fill(el, "Phone number", "+65 9876 5432");
    await submit(el);

    const phoneInput = field(el, "Phone number");
    expect(el.querySelector(`#${phoneInput.id}-error`)?.textContent.trim()).toBe("Phone number is invalid.");
  });

  it.each([
    [new ApiError("Profile update rejected.", 422, [{ loc: ["body", "unknown"], msg: "Unknown field." }]), "Profile update rejected."],
    [new ApiError("Profile service unavailable.", 503), "Profile service unavailable."],
    [new Error("network failure"), "Could not update your profile. Please try again."],
  ])("shows a form-level error when the API cannot attach an error to a visible field", async (failure, message) => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      role: "attendee",
      roles: ["attendee"],
    });
    authApi.updateProfile.mockRejectedValue(failure);

    [...el.querySelectorAll("button")].find((button) => button.textContent.trim() === "Edit profile").click();
    await nextTick();
    fill(el, "Full name", "Siti Updated");
    await submit(el);

    expect(el.querySelector('[role="alert"]')?.textContent.trim()).toBe(message);
  });

  // SCRUM-50 AC2: the profile shows full name, email, phone number and current role.
  it("shows the full name, email, phone number and current role", async () => {
    const { el } = await mountProfileView({
      id: "u2",
      full_name: "Marcus Lim",
      email: "coordinator@connectsphere.dev",
      phone_number: "+6590000002",
      role: "event_coordinator",
      roles: ["event_coordinator"],
      department: "Event Planning",
    });

    expect(el.textContent).toContain("Marcus Lim");
    expect(el.textContent).toContain("coordinator@connectsphere.dev");
    expect(el.textContent).toContain("+65 90000002");
    expect(el.textContent).toContain("Event Coordinator");
  });

  it("shows that no phone number was provided", async () => {
    const { el } = await mountProfileView({
      id: "u3",
      full_name: "Siti Rahman",
      email: "attendee@connectsphere.dev",
      phone_number: null,
      role: "attendee",
      roles: ["attendee"],
    });

    expect(el.textContent).toContain("Not provided");
  });

  it("shows the active role in the badge, not every role the account holds", async () => {
    const { el } = await mountProfileView({
      id: "u1",
      full_name: "Marcus Lim",
      email: "coordinator@connectsphere.dev",
      role: "venue_staff",
      roles: ["event_coordinator", "venue_staff"],
    });

    const badge = [...el.querySelectorAll("span")].find((node) => node.textContent.trim() === "Venue Staff");
    expect(badge.className).toContain("bg-bauhaus-yellow");
    const coordinatorBadge = [...el.querySelectorAll("span")].find(
      (node) => node.textContent.trim() === "Event Coordinator",
    );
    expect(coordinatorBadge.className).not.toContain("bg-bauhaus-yellow");
  });

  // SCRUM-50 AC3: internal staff see a department, organisers an organisation, attendees neither.
  // Both fields are populated in every case, so these prove the role decides what shows, not
  // whether a field happens to be null.
  it.each([
    ["event_coordinator", { department: true, organisation: false }],
    ["event_coordinator_lead", { department: true, organisation: false }],
    ["venue_staff", { department: true, organisation: false }],
    ["tech_support", { department: true, organisation: false }],
    ["safety_officer", { department: true, organisation: false }],
    ["event_organiser", { department: false, organisation: true }],
    ["attendee", { department: false, organisation: false }],
  ])("shows the right details for %s when both fields hold a value", async (role, shown) => {
    const { el } = await mountProfileView({
      id: "u2",
      full_name: "Marcus Lim",
      email: "someone@connectsphere.dev",
      role,
      roles: [role],
      department: "Event Planning",
      organisation_name: "Tan & Partners Events",
    });

    expect(el.textContent.includes("Department")).toBe(shown.department);
    expect(el.textContent.includes("Event Planning")).toBe(shown.department);
    expect(el.textContent.includes("Organisation")).toBe(shown.organisation);
    expect(el.textContent.includes("Tan & Partners Events")).toBe(shown.organisation);
  });

  it("follows the active role for an account that holds several roles", async () => {
    const profile = {
      id: "u1",
      full_name: "Olivia Tan",
      email: "organiser@connectsphere.dev",
      roles: ["event_organiser", "attendee"],
      organisation_name: "Tan & Partners Events",
    };

    const asAttendee = await mountProfileView({ ...profile, role: "attendee" });
    expect(asAttendee.el.textContent).not.toContain("Organisation");
    expect(asAttendee.el.textContent).not.toContain("Tan & Partners Events");

    document.body.innerHTML = "";
    const asOrganiser = await mountProfileView({ ...profile, role: "event_organiser" });
    expect(asOrganiser.el.textContent).toContain("Tan & Partners Events");
  });
});
