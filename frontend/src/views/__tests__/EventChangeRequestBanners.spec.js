import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi, registrationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Story 32: both sides see an open change request. Deciding it is story 37.
vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { safetyDecisions: vi.fn().mockResolvedValue([]), get: vi.fn(), history: vi.fn(), listComments: vi.fn(), addComment: vi.fn() },
  registrationsApi: { managedEvent: vi.fn() },
}));

const REASON = "Our sponsor wants more seats";
const OPEN_CHANGE = {
  id: "request-32", kind: "change", status: "open", reason: REASON, significant: true,
  changes: {
    event: [{ field: "expected_attendance", before: 80, after: 120 }],
    spaces: [{ space_id: "space-1", label: "Main hall", fields: [{ field: "layout_preference", before: "theatre", after: "banquet" }] }],
  },
  requested_by: { id: "organiser-1", full_name: "Priya Nair" }, requested_at: "2026-10-24T01:00:00Z",
};

function eventResponse(overrides = {}) {
  return {
    id: "event-32", name: "Partner Summit", status: "planning", version: 3, event_timezone: "Asia/Singapore",
    purpose: "Quarterly partner meeting", description: null,
    starts_at: "2026-12-12T02:00:00Z", ends_at: "2026-12-12T04:00:00Z", expected_attendance: 80,
    layout_preference: "theatre", facilities_required: [], accessibility_needs: null,
    preliminary_equipment_needs: null, registration_enabled: false, coordinator_id: "coordinator-1",
    organiser_id: "organiser-1", open_cancellation_request: null, open_change_request: null, ...overrides,
  };
}

const mountedApps = [];
// "Request changes" shows only before the event starts, so the fixtures' dates stay
// in the future only with the clock fixed before them (D78). Only Date is faked.
const TODAY = new Date("2026-10-20T02:00:00Z");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(TODAY);
  registrationsApi.managedEvent.mockResolvedValue({
    event_id: "event-32",
    effective_capacity: null,
    registered_count: 0,
    remaining_places: null,
    waitlist_count: 0,
    registrations: [],
  });
});

async function mount(response, { role, routeName, view }) {
  eventsApi.get.mockResolvedValue(response);
  eventsApi.history.mockResolvedValue({ entries: [] });
  eventsApi.listComments.mockResolvedValue({ comments: [] });
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.refreshToken = "refresh";
  auth.profile = { id: role === "event_organiser" ? "organiser-1" : "coordinator-1", full_name: "Someone", role };
  auth.sessionVerified = true;

  const { default: router } = await import("@/router");
  await router.push({ name: routeName, params: { id: response.id } });
  const { default: View } = await view();
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router);
  app.mount(el);
  mountedApps.push(app);
  await vi.waitFor(() => expect(el.textContent).toContain(response.name));
  await nextTick();
  return { el, router };
}

const mountOrganiser = (response) => mount(response, {
  role: "event_organiser", routeName: "event-detail", view: () => import("@/views/events/EventDetailView.vue"),
});
const mountCoordinator = (response) => mount(response, {
  role: "event_coordinator", routeName: "coordinator-event", view: () => import("@/views/events/CoordinatorEventView.vue"),
});
const button = (root, label) => [...root.querySelectorAll("button")].find((node) => node.textContent.trim() === label);

afterEach(() => {
  mountedApps.splice(0).forEach((app) => app.unmount());
  document.body.innerHTML = "";
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("organiser event page (story 32)", () => {
  it("offers Request changes, which opens the request form in change mode", async () => {
    const { el, router } = await mountOrganiser(eventResponse());

    button(el, "Request changes").click();

    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("event-request-change"));
    expect(router.currentRoute.value.params.id).toBe("event-32");
  });

  it.each([["returned"], ["cancelled"], ["draft"]])("doesn't offer it on a %s event", async (status) => {
    const { el } = await mountOrganiser(eventResponse({ status }));

    expect(button(el, "Request changes")).toBeUndefined();
  });

  it("explains why changes can't be requested while a cancellation request is open", async () => {
    const { el } = await mountOrganiser(eventResponse({
      open_cancellation_request: { id: "c1", kind: "cancellation", status: "open", reason: "x", requested_at: "2026-10-24T01:00:00Z" },
    }));

    expect(button(el, "Request changes")).toBeUndefined();
    expect(el.querySelector('[data-testid="change-request-blocked"]').textContent).toContain(
      "A cancellation request is open, so changes can't be requested. Ask your coordinator to reject it first.");
  });

  it("shows the open change request: each change, why and when", async () => {
    const { el } = await mountOrganiser(eventResponse({ open_change_request: OPEN_CHANGE }));

    const banner = el.querySelector('[data-testid="change-request-banner"]');
    expect(banner.textContent).toContain("Change requested");
    expect(banner.textContent).toContain("Expected attendance: 80 → 120");
    expect(banner.textContent).toContain("Main hall: layout: theatre → banquet");
    expect(banner.textContent).toContain(REASON);
    expect(banner.textContent).toContain("Nothing changes until your coordinator approves the request.");
    expect(button(el, "Request changes")).toBeUndefined();
  });
});

describe("coordinator event page (story 32)", () => {
  it("shows who asked, whether it is significant, each change and the comments, with story 37's decisions", async () => {
    const { el } = await mountCoordinator(eventResponse({ open_change_request: OPEN_CHANGE }));

    const banner = el.querySelector('[data-testid="change-request-banner"]');
    expect(banner.textContent).toContain("Changes requested by Priya Nair");
    expect(banner.textContent).toContain("Significant change");
    expect(banner.textContent).toContain("Expected attendance: 80 → 120");
    expect(banner.textContent).toContain("Main hall: layout: theatre → banquet");
    expect(banner.querySelector('[data-testid="change-request-comments"]').textContent).toBe(REASON);
    // Story 37 AC2: the banner now carries the coordinator's decision, and nothing else.
    expect([...banner.querySelectorAll("button")].map((b) => b.textContent.trim()))
      .toEqual(["Approve changes", "Reject changes"]);
  });

  it("labels an ordinary change as ordinary", async () => {
    const { el } = await mountCoordinator(eventResponse({
      open_change_request: { ...OPEN_CHANGE, significant: false },
    }));

    expect(el.querySelector('[data-testid="change-request-banner"]').textContent).toContain("Ordinary change");
  });

  it("shows no banner without an open change request", async () => {
    const { el } = await mountCoordinator(eventResponse());

    expect(el.querySelector('[data-testid="change-request-banner"]')).toBeNull();
  });
});
