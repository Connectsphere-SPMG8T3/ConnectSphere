import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 112: the assigned coordinator edits an event's ordinary details.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: {
    safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(),
    addComment: vi.fn(), editDetails: vi.fn(),
  },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "planning", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2099-11-12T02:00:00Z", ends_at: "2099-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    open_cancellation_request: null, open_reassignment_request: null, ...overrides,
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

const button = (root, label) => root.querySelector(`button[aria-label="${label}"]`);
const dialog = () => document.body.querySelector('[role="dialog"]');

async function typeInto(selector, text) {
  const control = dialog().querySelector(selector);
  control.value = text;
  control.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("Story 112 coordinator edits an event's details", () => {
  beforeEach(() => vi.clearAllMocks());

  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it.each(["under_review", "planning", "safety_review", "confirmed", "preparation"])(
    "offers the edit on a %s event (AC1)", async (status) => {
      const el = await mountView(eventResponse({ status }));

      expect(button(el, "Edit event details")).not.toBeNull();
    },
  );

  it.each(["returned", "rejected", "cancelled", "completed"])("does not offer it on a %s event (AC6)", async (status) => {
    const el = await mountView(eventResponse({ status }));

    expect(button(el, "Edit event details")).toBeNull();
  });

  it("saves only what changed, with the loaded version, and shows the saved event", async () => {
    const el = await mountView(eventResponse());
    eventsApi.editDetails.mockResolvedValue(eventResponse({ version: 4 }));
    eventsApi.get.mockResolvedValue(eventResponse({ version: 4, name: "Partner Summit 2027" }));

    button(el, "Edit event details").click();
    await nextTick();
    await typeInto("input", "Partner Summit 2027");
    button(document.body, "Save details").click();

    await vi.waitFor(() => expect(eventsApi.editDetails).toHaveBeenCalledWith(
      "event-1", { version: 3, name: "Partner Summit 2027" }, "access",
    ));
    await vi.waitFor(() => expect(dialog()).toBeNull());
    expect(el.textContent).toContain("Partner Summit 2027");
  });

  it("keeps the dialog open with the API's refusal", async () => {
    const el = await mountView(eventResponse());
    eventsApi.editDetails.mockRejectedValue(new ApiError("Significant changes go through a change request.", 422));

    button(el, "Edit event details").click();
    await nextTick();
    await typeInto("#edit-description", "Agreed offline");
    button(document.body, "Save details").click();

    await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]').textContent)
      .toContain("Significant changes go through a change request."));
    expect(dialog()).not.toBeNull();
  });

  it("offers a reload after a stale save, and reloading shows the newer event (AC4)", async () => {
    const el = await mountView(eventResponse());
    eventsApi.editDetails.mockRejectedValue(new ApiError("This event was updated by someone else. Reload.", 409));

    button(el, "Edit event details").click();
    await nextTick();
    await typeInto("#edit-description", "Mine");
    button(document.body, "Save details").click();
    await vi.waitFor(() => expect(button(document.body, "Reload event")).not.toBeNull());

    eventsApi.get.mockResolvedValue(eventResponse({ version: 4, name: "Partner Summit (renamed)" }));
    button(document.body, "Reload event").click();

    await vi.waitFor(() => expect(el.textContent).toContain("Partner Summit (renamed)"));
    expect(dialog()).toBeNull();
  });

  it("closes without saving on cancel", async () => {
    const el = await mountView(eventResponse());

    button(el, "Edit event details").click();
    await nextTick();
    button(document.body, "Cancel").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(eventsApi.editDetails).not.toHaveBeenCalled();
  });
});
