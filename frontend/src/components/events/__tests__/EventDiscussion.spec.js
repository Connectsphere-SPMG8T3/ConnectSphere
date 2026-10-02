import { createPinia, setActivePinia } from "pinia";
import { createApp, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EventDiscussion from "@/components/events/EventDiscussion.vue";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  eventsApi: { listComments: vi.fn(), addComment: vi.fn() },
}));

const COMMENT = {
  id: "c1", body: "Can we recce the hall on Friday?", created_at: "2026-10-02T03:00:00Z",
  author: { id: "o1", full_name: "Olivia Tan", role: "event_organiser" },
};
const mounted = [];

async function mountDiscussion(props = {}) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.token = "access";
  auth.profile = { id: "o1", role: "event_organiser", full_name: "Olivia Tan" };
  const el = document.createElement("div");
  document.body.appendChild(el);
  const app = createApp({ render: () => h(EventDiscussion, { eventId: "event-1", status: "under_review", ...props }) });
  app.use(pinia);
  app.mount(el);
  mounted.push(app);
  await vi.waitFor(() => expect(eventsApi.listComments).toHaveBeenCalled());
  await vi.waitFor(() => expect(document.body.textContent).not.toContain("Loading comments"));
}

async function type(text) {
  const textarea = document.querySelector("textarea");
  textarea.value = text;
  textarea.dispatchEvent(new Event("input"));
  await nextTick();
}

const postButton = () => document.querySelector('button[aria-label="Post comment"]');

describe("EventDiscussion (SCRUM-61)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    eventsApi.listComments.mockResolvedValue({ comments: [COMMENT] });
  });

  afterEach(() => {
    mounted.splice(0).forEach((app) => app.unmount());
    document.body.innerHTML = "";
  });

  it("shows each comment with its author, role and Singapore time", async () => {
    await mountDiscussion();

    const text = document.body.textContent;
    expect(text).toContain("Can we recce the hall on Friday?");
    expect(text).toContain("Olivia Tan");
    expect(text).toContain("Event Organiser");
    expect(text).toContain("11:00"); // 03:00Z is 11:00 in Singapore
  });

  it("shows an empty state when nobody has commented", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [] });
    await mountDiscussion();

    expect(document.body.textContent).toContain("No comments yet");
  });

  it("names a comment whose author was removed", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [{ ...COMMENT, author: null }] });
    await mountDiscussion();

    expect(document.body.textContent).toContain("Unknown user");
  });

  it("wraps long words so the thread never widens the page", async () => {
    eventsApi.listComments.mockResolvedValue({ comments: [{ ...COMMENT, body: "x".repeat(1000) }] });
    await mountDiscussion();

    // overflow-wrap: anywhere, unlike break-word, also lowers the min-content width, so the
    // organiser page's grid column can't grow to the word's full width (found at 1440px).
    expect(document.querySelector("[data-comment-body]").className).toContain("[overflow-wrap:anywhere]");
  });

  it("counts characters against the 1000 limit", async () => {
    await mountDiscussion();
    await type("Hello");

    expect(document.body.textContent).toContain("5 / 1000");
  });

  it("disables Post for whitespace", async () => {
    await mountDiscussion();
    await type("   \n ");

    expect(postButton().disabled).toBe(true);
  });

  it("posts the comment, appends it and clears the box", async () => {
    eventsApi.addComment.mockResolvedValue({ ...COMMENT, id: "c2", body: "Booked for 3pm." });
    await mountDiscussion();
    await type("  Booked for 3pm.  ");

    postButton().click();
    await vi.waitFor(() => expect(eventsApi.addComment).toHaveBeenCalledWith("event-1", "Booked for 3pm.", "access"));
    await vi.waitFor(() => expect(document.body.textContent).toContain("Booked for 3pm."));

    expect(document.querySelector("textarea").value).toBe("");
  });

  it("keeps the draft text when posting fails", async () => {
    eventsApi.addComment.mockRejectedValue(new Error("Comments are closed for this event. Reload."));
    await mountDiscussion();
    await type("Late question");

    postButton().click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());

    expect(document.querySelector('[role="alert"]').textContent).toContain("Comments are closed for this event. Reload.");
    expect(document.querySelector("textarea").value).toBe("Late question");
  });

  it("is read-only once the event is closed", async () => {
    await mountDiscussion({ status: "rejected" });

    expect(document.querySelector("textarea")).toBeNull();
    expect(document.body.textContent).toContain("This discussion is closed");
    expect(document.body.textContent).toContain("Can we recce the hall on Friday?");
  });
});
