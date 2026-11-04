// CR-100: the real edit form loads and submits the four new venue fields.
import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import VenueEditView from "@/views/venues/VenueEditView.vue";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", () => ({ venuesApi: { get: vi.fn(), update: vi.fn() } }));
const venue = { id: "v1", name: "Hall", location: "Campus", capacity: 50, opens_at: "08:00:00",
  closes_at: "22:00:00", layouts: [], facilities: [], accessibility_features: [],
  setup_minutes: 30, turnaround_minutes: 45, emergency_access: "East exit", restrictions: "No flames" };
let app;
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); });
afterEach(() => { app?.unmount(); document.body.innerHTML = ""; });

async function mount() {
  const pinia = createPinia(); setActivePinia(pinia);
  const auth = useAuthStore(); auth.token = "access"; auth.profile = { id: "staff", role: "venue_staff" };
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/venues/:id/edit", name: "venue-edit", component: { template: "<div />" } },
    { path: "/venues", name: "venue-search", component: { template: "<div />" } },
    { path: "/venues/:id", name: "venue-detail", component: { template: "<div />" } },
  ] });
  await router.push("/venues/v1/edit");
  venuesApi.get.mockResolvedValue(venue);
  const el = document.createElement("div"); document.body.appendChild(el);
  app = createApp(VenueEditView).use(pinia).use(router); app.mount(el);
  await vi.waitFor(() => expect(el.querySelector("form")).not.toBeNull());
  return { el, router };
}

function field(el, name) {
  const label = [...el.querySelectorAll("label")].find((node) => node.textContent.includes(name));
  return label.htmlFor ? el.querySelector(`#${label.htmlFor}`) : label.querySelector("textarea");
}
async function input(node, value) { node.value = value; node.dispatchEvent(new Event("input")); await nextTick(); }

it("loads the defaults and safety facts and saves their edited values", async () => {
  const { el, router } = await mount();
  expect(field(el, "Default setup").value).toBe("30");
  expect(field(el, "Default turnaround").value).toBe("45");
  expect(field(el, "Emergency access").value).toBe("East exit");
  expect(field(el, "Restrictions").value).toBe("No flames");
  expect(field(el, "Default setup").getAttribute("max")).toBeNull();
  expect(el.textContent).toContain("Existing bookings keep their own");
  await input(field(el, "Default setup"), "0");
  await input(field(el, "Default turnaround"), "1000000");
  await input(field(el, "Emergency access"), " West exit\nAssembly point ");
  await input(field(el, "Restrictions"), "");
  venuesApi.update.mockResolvedValue({ saved: true, venue, warnings: [] });
  el.querySelector("form").dispatchEvent(new Event("submit", { cancelable: true }));
  await vi.waitFor(() => expect(router.currentRoute.value.name).toBe("venue-detail"));
  expect(venuesApi.update).toHaveBeenCalledWith("v1", expect.objectContaining({ setup_minutes: 0,
    turnaround_minutes: 1000000, emergency_access: "West exit\nAssembly point", restrictions: null }), "access");
});

it("shows validation and sends nothing for an empty buffer", async () => {
  const { el } = await mount();
  await input(field(el, "Default setup"), "");
  el.querySelector("form").dispatchEvent(new Event("submit", { cancelable: true }));
  await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toContain("whole number"));
  expect(venuesApi.update).not.toHaveBeenCalled();
});
