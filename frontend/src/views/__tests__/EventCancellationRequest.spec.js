import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 84: the organiser asks to cancel their event from its page.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { get: vi.fn(), history: vi.fn(), listComments: vi.fn(), addComment: vi.fn(), requestCancellation: vi.fn() },
}));

const REASON = "Our keynote speaker has withdrawn";
const OPEN_REQUEST = {
  id: "request-1", kind: "cancellation", status: "open", reason: REASON,
  requested_by: { id: "organiser-1", full_name: "Priya Nair" }, requested_at: "2026-10-23T01:00:00Z",
};

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Annual Conference", status: "planning", event_timezone: "Asia/Singapore",
    starts_at: "2026-11-01T02:00:00Z", ends_at: "2026-11-01T07:00:00Z", expected_attendance: 150,
    facilities_required: [], registration_enabled: false, coordinator_id: "coordinator-1",
    open_cancellation_request: null, ...overrides,
  };
}

const mountedApps = [];

async function mountDetail(response, historyResponse = { entries: [] }) {
  eventsApi.history.mockResolvedValue(historyResponse);
  eventsApi.listComments.mockResolvedValue({ comments: [] });
  eventsApi.get.mockResolvedValue(response);
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.token = "access";
  authStore.refreshToken = "refresh";
  authStore.profile = { id: "organiser-1", full_name: "Priya Nair", role: "event_organiser" };
  authStore.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: "event-detail", params: { id: response.id } });
  const { default: EventDetailView } = await import("@/views/events/EventDetailView.vue");
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(EventDetailView).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return el;
}

function button(root, label) {
  return [...root.querySelectorAll("button")].find((node) => node.textContent.trim() === label);
}

function dialog() {
  return document.body.querySelector('[role="dialog"]');
}

async function typeReason(text) {
  const field = dialog().querySelector("textarea");
  field.value = text;
  field.dispatchEvent(new Event("input"));
  await nextTick();
}

describe("Story 84 organiser requests cancellation", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it.each(["submitted", "under_review", "returned", "planning", "safety_review", "confirmed", "preparation"])(
    "offers Request cancellation while the event is %s",
    async (status) => {
      const el = await mountDetail(eventResponse({ status }));
      expect(button(el, "Request cancellation")).toBeTruthy();
    },
  );

  it.each(["draft", "rejected", "cancelled", "completed"])("doesn't offer it while the event is %s", async (status) => {
    const el = await mountDetail(eventResponse({ status }));
    expect(button(el, "Request cancellation")).toBeUndefined();
  });

  it("shows the open request, with its reason, instead of the button", async () => {
    const el = await mountDetail(eventResponse({ open_cancellation_request: OPEN_REQUEST }));

    const banner = el.querySelector('[data-testid="cancellation-request-banner"]');
    expect(banner.textContent).toContain("Cancellation requested");
    expect(banner.textContent).toContain(REASON);
    expect(banner.textContent).toContain("Your arrangements stay in place until your coordinator decides.");
    expect(button(el, "Request cancellation")).toBeUndefined();
  });

  it("sends the trimmed reason, then shows the request", async () => {
    const el = await mountDetail(eventResponse());
    eventsApi.requestCancellation.mockResolvedValue(OPEN_REQUEST);

    button(el, "Request cancellation").click();
    await nextTick();
    expect(button(dialog(), "Send request").disabled).toBe(true);
    await typeReason(`  ${REASON}  `);
    eventsApi.get.mockResolvedValue(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    button(dialog(), "Send request").click();

    await vi.waitFor(() => expect(el.querySelector('[data-testid="cancellation-request-banner"]')).toBeTruthy());
    expect(eventsApi.requestCancellation).toHaveBeenCalledWith("event-1", REASON, "access");
    expect(dialog()).toBeNull();
    expect(eventsApi.history).toHaveBeenCalledTimes(2);
  });

  it("still shows the request when the history can't be reloaded", async () => {
    const el = await mountDetail(eventResponse());
    eventsApi.requestCancellation.mockResolvedValue(OPEN_REQUEST);

    button(el, "Request cancellation").click();
    await nextTick();
    await typeReason(REASON);
    eventsApi.get.mockResolvedValue(eventResponse({ open_cancellation_request: OPEN_REQUEST }));
    eventsApi.history.mockRejectedValue(new Error("Network down"));
    button(dialog(), "Send request").click();

    await vi.waitFor(() => expect(eventsApi.history).toHaveBeenCalledTimes(2));
    expect(el.querySelector('[data-testid="cancellation-request-banner"]')).toBeTruthy();
    expect(el.querySelector('[role="alert"]')).toBeNull();
  });

  it("keeps the dialog open with the API's reason when the request is refused", async () => {
    const el = await mountDetail(eventResponse());
    eventsApi.requestCancellation.mockRejectedValue(
      new ApiError("A cancellation request is already open for this event.", 409),
    );

    button(el, "Request cancellation").click();
    await nextTick();
    await typeReason(REASON);
    button(dialog(), "Send request").click();

    await vi.waitFor(() => expect(dialog().querySelector('[role="alert"]')).toBeTruthy());
    expect(dialog().textContent).toContain("A cancellation request is already open for this event.");
  });

  it("closes the dialog without sending anything on Cancel", async () => {
    const el = await mountDetail(eventResponse());

    button(el, "Request cancellation").click();
    await nextTick();
    button(dialog(), "Keep event").click();
    await nextTick();

    expect(dialog()).toBeNull();
    expect(eventsApi.requestCancellation).not.toHaveBeenCalled();
  });
});
