import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
  eventsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), submit: vi.fn(), history: vi.fn() },
}));

function eventResponse(overrides = {}) {
  return {
    id: "event-1",
    name: "Annual Conference",
    status: "submitted",
    event_timezone: "Asia/Singapore",
    starts_at: "2026-11-01T02:00:00Z",
    ends_at: "2026-11-01T07:00:00Z",
    expected_attendance: 150,
    facilities_required: [],
    registration_enabled: false,
    coordinator_id: null,
    ...overrides,
  };
}

const mountedApps = [];

async function mountDetail(response, historyResponse = { entries: [] }) {
  eventsApi.history.mockResolvedValue(historyResponse);
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

describe("EventDetailView status", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  it("shows the same plain-language status label as the dashboard, not the raw status (LC-R3)", async () => {
    const el = await mountDetail(eventResponse({ status: "submitted" }));

    expect(el.textContent).toContain("Awaiting assignment");
    expect(el.textContent).not.toMatch(/\bsubmitted\b/);
  });

  it("never describes a planning event as approved (QA2-8)", async () => {
    const el = await mountDetail(eventResponse({ status: "planning" }));

    expect(el.textContent).toContain("Planning");
    expect(el.textContent).not.toMatch(/\bapproved\b/i);
  });
});

describe("EventDetailView decision and history (SCRUM-34, SCRUM-52)", () => {
  afterEach(() => {
    mountedApps.splice(0).forEach((app) => app.unmount());
  });

  beforeEach(() => {
    document.body.innerHTML = "";
    vi.clearAllMocks();
  });

  const rejection = {
    id: "h2", from_status: "under_review", to_status: "rejected", reason: "Venue unavailable on that date",
    at: "2026-09-24T06:05:00Z", actor: { id: "c1", full_name: "Marcus Lim" },
  };

  it("shows the organiser why their request was rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    await vi.waitFor(() => expect(el.querySelector('[data-testid="rejection-notice"]')).not.toBeNull());
    const notice = el.querySelector('[data-testid="rejection-notice"]');
    expect(notice.textContent).toContain("Venue unavailable on that date");
    expect(notice.textContent).toContain("can't be resubmitted");
  });

  it("offers no resubmit or edit action on a rejected request", async () => {
    const el = await mountDetail(eventResponse({ status: "rejected" }), { entries: [rejection] });

    expect(el.textContent).not.toMatch(/resubmit request|edit request/i);
  });

  it("lists the status history", async () => {
    const el = await mountDetail(eventResponse({ status: "planning" }), {
      entries: [{ id: "h1", from_status: "under_review", to_status: "planning", reason: null,
        at: "2026-09-23T03:00:00Z", actor: { id: "c1", full_name: "Marcus Lim" } }],
    });

    await vi.waitFor(() => expect(el.textContent).toContain("Marcus Lim"));
    expect(el.textContent).toContain("History");
  });

  it("shows no rejection notice for an event that isn't rejected", async () => {
    const el = await mountDetail(eventResponse({ status: "under_review" }));

    expect(el.querySelector('[data-testid="rejection-notice"]')).toBeNull();
  });
});
