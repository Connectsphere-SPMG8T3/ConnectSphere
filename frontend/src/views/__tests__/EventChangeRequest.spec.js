import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    list: vi.fn(), get: vi.fn(), create: vi.fn(), createSpace: vi.fn(), updateSpace: vi.fn(), removeSpace: vi.fn(),
    update: vi.fn(), remove: vi.fn(), submit: vi.fn(), resubmit: vi.fn(), requestChange: vi.fn(), history: vi.fn(),
    comments: vi.fn(),
  },
}));

// Story 32: the organiser proposes changes in the request form's change mode.
function plannedEvent(overrides = {}) {
  return {
    id: "event-32", name: "Partner Summit", status: "planning", event_timezone: "Asia/Singapore",
    purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-12-01T02:00:00Z", ends_at: "2026-12-01T04:00:00Z",
    expected_attendance: 80, layout_preference: "theatre", facilities_required: [],
    spaces: [{ id: "space-1", version: 1, label: "Main venue", expected_pax: 80, layout_preference: "theatre", facilities_required: [] }],
    accessibility_needs: null, preliminary_equipment_needs: null, registration_enabled: false,
    registration_capacity: null, registration_opens_at: null, registration_closes_at: null,
    re_registration_allowed: true, waitlist_enabled: true,
    coordinator_id: "coordinator-1", version: 5, open_change_request: null, open_cancellation_request: null,
    ...overrides,
  };
}

const mountedApps = [];

async function mountChangeForm(detail) {
  eventsApi.get.mockResolvedValue(detail);
  eventsApi.history.mockResolvedValue({ entries: [] });
  eventsApi.comments.mockResolvedValue({ comments: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-request-change", params: { id: detail.id } });
  const { default: View } = await import("@/views/events/EventRequestView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  return { el, router };
}

async function mountLoaded(detail = plannedEvent()) {
  const mounted = await mountChangeForm(detail);
  await vi.waitFor(() => expect(mounted.el.querySelector("input").value).toBe(detail.name));
  await nextTick();
  return mounted;
}

const labelled = (el, label) =>
  [...el.querySelectorAll("label")].find((node) => node.textContent.trim().startsWith(label));
const controlFor = (el, label) => document.getElementById(labelled(el, label).getAttribute("for"));
const buttonByText = (root, text) => [...root.querySelectorAll("button")].find((node) => node.textContent.trim() === text);
const dialog = () => document.querySelector('[role="dialog"]');

async function type(input, value) {
  input.value = value;
  input.dispatchEvent(new Event("input"));
  await nextTick();
}

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("EventRequestView change mode (story 32)", () => {
  it("opens prefilled, without the draft, submit or space add/remove controls", async () => {
    const { el } = await mountLoaded();

    expect(el.querySelector("h1").textContent).toContain("Request changes");
    expect(controlFor(el, "Expected attendance").value).toBe("80");
    for (const text of ["Save draft", "Submit request", "Copy space", "Remove space", "Add space request"]) {
      expect(buttonByText(el, text)).toBeUndefined();
    }
    expect(buttonByText(el, "Send change request").disabled).toBe(true);
  });

  it("does not offer withdrawal cutoff changes in change-request mode", async () => {
    const event = plannedEvent({
      registration_enabled: true,
      registration_capacity: 80,
      registration_opens_at: "2026-11-01T01:00:00Z",
      registration_closes_at: "2026-11-30T01:00:00Z",
      withdrawal_closes_at: "2026-12-01T01:30:00Z",
    });
    const { el } = await mountLoaded(event);

    expect(labelled(el, "Withdrawal cutoff")).toBeUndefined();
  });

  it("sends only the changed fields with the reason and the version it was filled in against", async () => {
    eventsApi.requestChange.mockResolvedValue({ id: "r1", kind: "change", status: "open" });
    const { el, router } = await mountLoaded(plannedEvent({
      registration_enabled: true,
      registration_capacity: 80,
      registration_opens_at: "2026-11-01T01:00:00Z",
      registration_closes_at: "2026-11-30T01:00:00Z",
      withdrawal_closes_at: "2026-12-01T01:30:00Z",
    }));

    await type(controlFor(el, "Expected attendance"), "120");
    await type(controlFor(el, "Expected pax"), "120");
    buttonByText(el, "Send change request").click();
    await nextTick();

    expect(dialog().textContent).toContain("Expected attendance");
    expect(dialog().textContent).toContain("80 → 120");
    expect(dialog().textContent).toContain("Main venue: attendance");
    await type(dialog().querySelector("textarea"), "Sponsor wants more seats");
    buttonByText(dialog(), "Send change request").click();

    await vi.waitFor(() => expect(eventsApi.requestChange).toHaveBeenCalledTimes(1));
    expect(eventsApi.requestChange).toHaveBeenCalledWith("event-32", {
      reason: "Sponsor wants more seats",
      version: 5,
      event: { expected_attendance: 120 },
      spaces: [{ id: "space-1", expected_pax: 120 }],
    }, "access");
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-detail"));
  });

  it("keeps the organiser's inputs and shows the API's answer when the request is refused", async () => {
    eventsApi.requestChange.mockRejectedValue(new ApiError("This event was updated by someone else. Reload.", 409));
    const { el } = await mountLoaded();

    await type(controlFor(el, "Expected attendance"), "120");
    buttonByText(el, "Send change request").click();
    await nextTick();
    await type(dialog().querySelector("textarea"), "Sponsor wants more seats");
    buttonByText(dialog(), "Send change request").click();

    await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]').textContent)
      .toContain("This event was updated by someone else. Reload."));
    expect(controlFor(el, "Expected attendance").value).toBe("120");
  });

  it.each([
    ["a returned request", { status: "returned" }],
    ["an event with an open cancellation request", { open_cancellation_request: { id: "c1" } }],
    ["an event with an open change request", { open_change_request: { id: "r1" } }],
  ])("sends %s back to the event page", async (_label, overrides) => {
    const { router } = await mountChangeForm(plannedEvent(overrides));

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-detail"));
    expect(eventsApi.requestChange).not.toHaveBeenCalled();
  });
});
