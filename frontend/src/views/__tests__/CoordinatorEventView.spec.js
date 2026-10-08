import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toastState } from "@/composables/useToast";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { get: vi.fn(), history: vi.fn(), approve: vi.fn(), reject: vi.fn(), returnForAmendment: vi.fn(), sendForSafetyCheck: vi.fn(), listComments: vi.fn(), addComment: vi.fn() },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "under_review", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-11-12T02:00:00Z", ends_at: "2026-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    ...overrides,
  };
}

const mountedApps = [];

async function mountView(response) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  eventsApi.listComments.mockResolvedValue({ comments: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "c1", full_name: "Marcus Lim", role: "event_coordinator" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "coordinator-event", params: { id: response.id } });
  const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

const button = (label) => document.querySelector(`button[aria-label="${label}"]`);

describe("CoordinatorEventView (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("SCRUM-82 disables send and names missing arrangements", async () => {
    const el = await mountView(eventResponse({status: "planning", safety_readiness: {ready: false, missing: ["Technical status is not Ready."]}, registration_enabled: true, registration_capacity: 80}));
    const send = button("Send for safety check"); expect(send.disabled).toBe(true);
    expect(document.getElementById(send.getAttribute("aria-describedby")).textContent).toContain("Technical status is not Ready.");
    expect(el.textContent).toContain("For information"); expect(el.textContent).toContain("80");
  });
  it("SCRUM-82 sends after confirmation and removes coordinator actions", async () => {
    const el = await mountView(eventResponse({status: "planning", safety_readiness: {ready: true, missing: []}}));
    eventsApi.sendForSafetyCheck.mockResolvedValue(eventResponse({status: "safety_review"}));
    button("Send for safety check").click(); await nextTick();
    expect(document.body.textContent).toContain("Send for safety check?");
    button("Send").click(); await vi.waitFor(() => expect(el.textContent).toContain("Safety review"));
    expect(button("Send for safety check")).toBeNull(); expect(eventsApi.sendForSafetyCheck).toHaveBeenCalledTimes(1);
    expect(toastState.value.message).toBe("Sent for safety check");
  });
  it("SCRUM-82 refreshes missing arrangements after a stale-page refusal", async () => {
    const ready = eventResponse({status: "planning", safety_readiness: {ready: true, missing: []}});
    const el = await mountView(ready);
    eventsApi.sendForSafetyCheck.mockRejectedValue(new ApiError("Not ready for safety check: Technical status is not Ready.", 409));
    eventsApi.get.mockResolvedValue({...ready, safety_readiness: {ready: false, missing: ["Technical status is not Ready."]}});
    button("Send for safety check").click(); await nextTick(); button("Send").click();
    await vi.waitFor(() => expect(button("Send for safety check").disabled).toBe(true));
    expect(el.textContent).toContain("Not ready for safety check: Technical status is not Ready.");
    expect(eventsApi.get).toHaveBeenCalledTimes(2);
  });
  it("SCRUM-82 has no send or information block during safety review", async () => {
    const el = await mountView(eventResponse({status: "safety_review"}));
    expect(button("Send for safety check")).toBeNull(); expect(el.textContent).not.toContain("For information");
  });
  it("shows the event's discussion thread (SCRUM-61)", async () => {
    const el = await mountView(eventResponse());

    await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalledWith("event-1", "access"));
    expect(el.textContent).toContain("Discussion");
  });

  it("offers approve and reject for a request under review", async () => {
    const el = await mountView(eventResponse());

    expect(el.textContent).toContain("Under review");
    expect(button("Approve request")).not.toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it("offers only reject while planning", async () => {
    await mountView(eventResponse({ status: "planning" }));

    expect(button("Approve request")).toBeNull();
    expect(button("Open reject dialog")).not.toBeNull();
  });

  it.each(["returned", "confirmed", "rejected", "cancelled", "completed", "submitted"])(
    "offers no decision when the request is %s",
    async (status) => {
      await mountView(eventResponse({ status }));

      expect(button("Approve request")).toBeNull();
      expect(button("Open reject dialog")).toBeNull();
      expect(button("Open return dialog")).toBeNull();
    },
  );

  it("offers return for a request under review, and not while planning", async () => {
    await mountView(eventResponse());
    expect(button("Open return dialog")).not.toBeNull();

    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    await mountView(eventResponse({ status: "planning" }));
    expect(button("Open return dialog")).toBeNull();
  });

  it("returns the request with the message and flagged fields, then shows it waiting on the organiser", async () => {
    const el = await mountView(eventResponse());
    eventsApi.returnForAmendment.mockResolvedValue(eventResponse({
      status: "returned", version: 4,
      amendment: { id: "a1", message: "Confirm attendance", flagged_fields: ["expected_attendance"], returned_at: "2026-09-24T03:00:00Z" },
    }));

    button("Open return dialog").click();
    await nextTick();
    const textarea = document.querySelector('[role="dialog"] textarea');
    textarea.value = "Confirm attendance";
    textarea.dispatchEvent(new Event("input"));
    const box = [...document.querySelectorAll('input[type="checkbox"]')]
      .find((input) => input.closest("label").textContent.includes("Expected attendance"));
    box.checked = true;
    box.dispatchEvent(new Event("change"));
    await nextTick();
    button("Return request").click();

    await vi.waitFor(() => expect(eventsApi.returnForAmendment).toHaveBeenCalledWith(
      "event-1", { message: "Confirm attendance", flagged_fields: ["expected_attendance"] }, "access",
    ));
    await vi.waitFor(() => expect(el.textContent).toContain("Waiting for the organiser to amend"));
    expect(el.textContent).toContain("Returned for amendment");
    expect(button("Approve request")).toBeNull();
    expect(button("Open return dialog")).toBeNull();
  });

  it("approves after confirmation and shows Planning", async () => {
    const el = await mountView(eventResponse());
    eventsApi.approve.mockResolvedValue(eventResponse({ status: "planning", version: 4 }));

    button("Approve request").click();
    await nextTick();
    expect(document.body.textContent).toContain("This does not confirm the event");
    button("Approve").click();

    await vi.waitFor(() => expect(eventsApi.approve).toHaveBeenCalledWith("event-1", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Planning"));
    expect(button("Approve request")).toBeNull();
  });

  it("rejects with the typed reason", async () => {
    const el = await mountView(eventResponse());
    eventsApi.reject.mockResolvedValue(eventResponse({ status: "rejected", version: 4 }));

    button("Open reject dialog").click();
    await nextTick();
    const textarea = document.querySelector('[role="dialog"] textarea');
    textarea.value = "Venue unavailable";
    textarea.dispatchEvent(new Event("input"));
    await nextTick();
    button("Reject request").click();

    await vi.waitFor(() => expect(eventsApi.reject).toHaveBeenCalledWith("event-1", "Venue unavailable", "access"));
    await vi.waitFor(() => expect(el.textContent).toContain("Rejected"));
  });

  it("shows why the page can't load", async () => {
    eventsApi.get.mockRejectedValue(Object.assign(new Error("Only the event's assigned coordinator can do this."), { status: 403 }));
    eventsApi.history.mockResolvedValue({ entries: [] });
    const pinia = createPinia();
    setActivePinia(pinia);
    const auth = useAuthStore();
    auth.token = "access";
    auth.profile = { id: "c9", full_name: "Other", role: "event_coordinator" };
    auth.sessionVerified = true;
    const { default: router } = await import("@/router");
    await router.push({ name: "coordinator-event", params: { id: "event-1" } });
    const { default: View } = await import("@/views/events/CoordinatorEventView.vue");
    const el = document.createElement("div");
    document.body.appendChild(el);
    const app = createApp(View).use(pinia).use(router);
    app.mount(el);
    mountedApps.push(app);

    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("assigned coordinator"));
  });

  it("reloads when the route param id changes", async () => {
    const el = await mountView(eventResponse({ id: "event-1", name: "First Event" }));
    eventsApi.get.mockResolvedValue(eventResponse({ id: "event-2", name: "Second Event" }));

    const { default: router } = await import("@/router");
    await router.push({ name: "coordinator-event", params: { id: "event-2" } });

    await vi.waitFor(() => expect(el.textContent).toContain("Second Event"));
  });
});

