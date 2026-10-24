import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 84: the assigned coordinator sees the organiser's open request. Deciding it is story 115.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(), addComment: vi.fn() },
}));

const REASON = "Our keynote speaker has withdrawn";

function eventResponse(overrides = {}) {
  return {
    id: "event-1", name: "Partner Summit", status: "confirmed", version: 3,
    event_timezone: "Asia/Singapore", purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-11-12T02:00:00Z", ends_at: "2026-11-12T04:00:00Z", expected_attendance: 12,
    layout_preference: "boardroom", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, coordinator_id: "c1", organiser_id: "o1",
    open_cancellation_request: null, ...overrides,
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

describe("Story 84 coordinator sees an open cancellation request", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows who asked, why, and that arrangements stay held", async () => {
    const el = await mountView(eventResponse({
      open_cancellation_request: {
        id: "request-1", kind: "cancellation", status: "open", reason: REASON,
        requested_by: { id: "o1", full_name: "Priya Nair" }, requested_at: "2026-10-23T01:00:00Z",
      },
    }));

    const banner = el.querySelector('[data-testid="cancellation-request-banner"]');
    expect(banner.textContent).toContain("Cancellation requested by Priya Nair");
    expect(banner.textContent).toContain(REASON);
    const comments = banner.querySelector('[data-testid="cancellation-request-comments"]');
    expect(comments.previousElementSibling.textContent.trim()).toBe("Comments:");
    expect(comments.textContent).toBe(REASON);
    expect(banner.textContent).toContain("Arrangements stay held until you decide.");
    expect(banner.querySelector("button")).toBeNull();
  });

  it("shows nothing when no request is open", async () => {
    const el = await mountView(eventResponse());

    expect(el.querySelector('[data-testid="cancellation-request-banner"]')).toBeNull();
  });
});
