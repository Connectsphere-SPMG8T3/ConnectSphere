import { createApp, h, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuthPageLayout from "@/components/common/AuthPageLayout.vue";
import EventPlanIllustration from "@/components/common/EventPlanIllustration.vue";
import TicketIllustration from "@/components/common/TicketIllustration.vue";

const mounted = [];

function allowMotion(allowed) {
  window.matchMedia = vi.fn(() => ({
    matches: !allowed,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

async function mount(component, props = {}, slots = {}) {
  const empty = { render: () => null };
  // The footer links to named routes, so the stub router needs them.
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/signup/:role", name: "signup", component: empty },
      { path: "/:any(.*)", component: empty },
    ],
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(component, props, slots) }).use(router);
  app.mount(el);
  mounted.push(app);
  await nextTick();
  return el;
}

const ticked = (el) => el.querySelectorAll('[data-done="true"]').length;

describe("auth and landing illustrations", () => {
  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
    delete window.matchMedia;
    vi.useRealTimers();
  });

  it("shows the event plan with the first three items done when still", async () => {
    const el = await mount(EventPlanIllustration);

    expect(el.textContent).toContain("Event plan");
    expect(el.querySelectorAll("li")).toHaveLength(5);
    expect(ticked(el)).toBe(3);
  });

  it("ticks the plan off one item at a time when animated", async () => {
    vi.useFakeTimers();
    allowMotion(true);
    const el = await mount(EventPlanIllustration, { animated: true });

    expect(ticked(el)).toBe(0);
    vi.advanceTimersByTime(900);
    await nextTick();
    expect(ticked(el)).toBe(1);
    vi.advanceTimersByTime(900 * 4);
    await nextTick();
    expect(ticked(el)).toBe(5);
  });

  it("keeps the plan still when the visitor prefers reduced motion", async () => {
    vi.useFakeTimers();
    allowMotion(false);
    const el = await mount(EventPlanIllustration, { animated: true });

    vi.advanceTimersByTime(900 * 3);
    await nextTick();
    expect(ticked(el)).toBe(3);
  });

  it("shows a ticket that rocks only when animated and motion is allowed", async () => {
    vi.useFakeTimers();
    allowMotion(true);
    const el = await mount(TicketIllustration, { animated: true });
    const ticket = el.firstElementChild;

    expect(el.textContent).toContain("Admit one");
    expect(el.textContent).toContain("Spot saved");
    const before = ticket.className;
    vi.advanceTimersByTime(1600);
    await nextTick();
    expect(ticket.className).not.toBe(before);
  });

  it("types the greeting into the speech bubble beside the form", async () => {
    vi.useFakeTimers();
    allowMotion(true);
    const el = await mount(AuthPageLayout, { greeting: "Hi there!", illustration: "plan" }, { default: () => h("form", "the form") });

    const panel = el.querySelector('[data-testid="auth-illustration"]');
    expect(panel.getAttribute("aria-hidden")).toBe("true");
    expect(panel.textContent).toContain("Event plan");
    const bubble = panel.querySelector('[data-testid="speech-bubble"]');
    expect(bubble.textContent.trim()).toBe("");
    vi.advanceTimersByTime(45 * 2);
    await nextTick();
    expect(bubble.textContent.trim()).toBe("Hi");
    vi.advanceTimersByTime(45 * 20);
    await nextTick();
    expect(bubble.textContent.trim()).toBe("Hi there!");
    expect(el.querySelector("main form")?.textContent).toBe("the form");
  });

  it("shows the whole greeting at once when the visitor prefers reduced motion", async () => {
    allowMotion(false);
    const el = await mount(AuthPageLayout, { greeting: "Hi there!" }, { default: () => h("form") });

    expect(el.querySelector('[data-testid="speech-bubble"]').textContent.trim()).toBe("Hi there!");
    expect(el.querySelector('[data-testid="auth-illustration"]').textContent).toContain("Admit one");
  });
});
