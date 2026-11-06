// Organiser dashboard checks against the real browser and backend.
import { API_URL, expect, seedSession, test } from "./support/fixtures.js";

const isEventsRequest = (url) => new URL(url).pathname === `${new URL(API_URL).pathname}/events`;
const authHeaders = (session) => ({ Authorization: ["Bearer", session.token].join(" ") });

async function createDraft(page, session, name) {
  const response = await page.request.post(`${API_URL}/events`, {
    headers: authHeaders(session),
    data: { name },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function discardDraft(page, session, eventId) {
  let response;
  try {
    response = await page.request.delete(`${API_URL}/events/${eventId}`, {
      headers: authHeaders(session),
    });
  } catch (error) {
    const remaining = await page.request.get(`${API_URL}/events/${eventId}`, {
      headers: authHeaders(session),
    });
    if (remaining.status() === 404) return;
    throw error;
  }
  expect(response.status()).toBe(204);
}

async function discardDrafts(page, session, eventIds) {
  const failures = [];
  for (const eventId of eventIds.filter(Boolean)) {
    try {
      await discardDraft(page, session, eventId);
    } catch (error) {
      failures.push(error);
    }
  }
  if (failures.length) throw new AggregateError(failures, "Failed to clean up test drafts.");
}

const uniqueName = (prefix) => `${prefix} ${Date.now()} ${Math.random().toString(36).slice(2, 8)}`;

test("TC-ORG-003 combined filters narrow the loaded collection and can be cleared", async ({ page, sharedSessions }) => {
  const session = await sharedSessions("event_organiser");
  const response = await page.request.get(`${API_URL}/events`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  expect(response.status()).toBe(200);
  const events = await response.json();
  const source = events.find((event) => event.status === "planning" && event.name);
  expect(source).toBeTruthy();

  await seedSession(page, session);
  await page.goto("/dashboard/organiser?tab=events");
  await expect(page.getByRole("heading", { name: "Find my event" })).toBeVisible();
  await expect(page.locator("[data-event-name] h3").first()).toBeVisible();
  const initialCount = await page.locator("[data-event-name] h3").count();
  const listRequests = [];
  page.on("request", (request) => {
    if (request.method() === "GET" && isEventsRequest(request.url())) listRequests.push(request.url());
  });

  await page.getByRole("button", { name: "Filter events by status" }).click();
  await page.locator('input[type="checkbox"][value="planning"]').check();
  const search = page.locator('input[aria-label="Search events"]');
  await search.fill(source.name.slice(0, 3));
  const results = page.locator("[data-event-name] h3");
  await expect(results.first()).toContainText(source.name.slice(0, 3));
  for (const result of await results.allTextContents()) {
    expect(result.toLocaleLowerCase()).toContain(source.name.slice(0, 3).toLocaleLowerCase());
  }
  expect(listRequests).toHaveLength(0);

  await search.fill("no-such-organiser-event");
  await expect(page.getByText("No matching events", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear", exact: true }).click();
  await expect(results).toHaveCount(initialCount);
  expect(listRequests).toHaveLength(0);
});

test("TC-ORG-006 an events API failure is shown without signing out or displaying empty success", async ({
  page,
  sharedSessions,
}) => {
  const session = await sharedSessions("event_organiser");
  await seedSession(page, session);
  await page.route(isEventsRequest, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Service unavailable" }),
    }),
  );

  await page.goto("/dashboard/organiser");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("No drafts", { exact: true })).toHaveCount(0);
  await expect(page.getByText("No submitted requests", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("connectsphere.session"))).toBeTruthy();
});

test("TC-ORG-006 loading is distinct from a successful empty result", async ({ page, sharedSessions }) => {
  const session = await sharedSessions("event_organiser");
  await seedSession(page, session);
  await page.route(isEventsRequest, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 750));
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await page.goto("/dashboard/organiser?tab=events");
  await expect(page.getByRole("status")).toContainText("Loading events...");
  await expect(page.getByText("No event requests yet", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("TC-ORG-011 a status count opens the Events view filtered to that status", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/dashboard/organiser");
  const planning = page.locator('[data-status-group="planning"]');
  await expect(planning).toBeVisible();
  await planning.getByRole("button", { name: "View all Planning events" }).click();
  await expect(page).toHaveURL(/tab=events/);
  await expect(page).toHaveURL(/status=planning/);
  await expect(page.getByRole("button", { name: "Filter events by status" })).toContainText("Planning");
});

test("TC-ORG-005 an organiser event page links back to the Events view", async ({ page, sharedSessions }) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/dashboard/organiser");
  const event = page.locator('[data-status-group="planning"] a[data-event-row]').first();
  await expect(event).toBeVisible();
  const eventName = (await event.getAttribute("aria-label")).replace(/^Open /, "");
  await event.click();
  await expect(page).toHaveURL(/\/events\/[^/]+$/);
  await expect(page.locator('a[aria-label="Events"]')).toHaveClass(/bg-bauhaus-yellow/);
  await expect(page.locator('a[aria-label="Overview"]')).not.toHaveClass(/bg-bauhaus-yellow/);
  const breadcrumb = page.locator('nav[aria-label="Breadcrumb"]');
  await expect(breadcrumb).toContainText("Dashboard");
  const eventsLink = breadcrumb.getByRole("link", { name: "Events" });
  await expect(eventsLink).toBeVisible();
  await expect(breadcrumb).toContainText(eventName);
  await eventsLink.click();
  await expect(page).toHaveURL(/dashboard\/organiser\?tab=events/);
});

test("TC-EVENT-052 a blank request remains available when the organiser owns no events", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.route(isEventsRequest, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  await page.goto("/dashboard/organiser?tab=events");
  await expect(page.getByText("No event requests yet", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New event request" }).click();
  await expect(page).toHaveURL(/\/events\/new$/);
  expect(new URL(page.url()).searchParams.has("id")).toBe(false);
});

test("TC-EVENT-056 a template draft has its own identity and creation history", async ({ page, sharedSessions }) => {
  const session = await sharedSessions("event_organiser");
  let source;
  let clone;
  try {
    source = await createDraft(page, session, uniqueName("TC-EVENT-056 source"));
    const cloneResponse = await page.request.post(`${API_URL}/events/${source.id}/clone`, {
      headers: authHeaders(session),
    });
    expect(cloneResponse.status()).toBe(201);
    clone = await cloneResponse.json();

    expect(clone.id).not.toBe(source.id);
    expect(clone.organiser_id).toBe(session.profile.id);
    expect(clone.status).toBe("draft");
    const historyResponse = await page.request.get(`${API_URL}/events/${clone.id}/history`, {
      headers: authHeaders(session),
    });
    expect(historyResponse.status()).toBe(200);
    const history = await historyResponse.json();
    expect(history.entries).toHaveLength(1);
    expect(history.entries[0]).toMatchObject({ from_status: null, to_status: "draft" });
  } finally {
    await discardDrafts(page, session, [clone?.id, source?.id]);
  }
});

test("TC-ORG-006 a saved title appears once on the dashboard", async ({ page, sharedSessions }) => {
  const session = await sharedSessions("event_organiser");
  const originalName = uniqueName("TC-ORG-006 draft");
  const updatedName = `${originalName} updated`;
  let event;
  try {
    event = await createDraft(page, session, originalName);
    await seedSession(page, session);
    await page.goto(`/events/new?id=${event.id}`);
    const title = page.getByLabel("Event title");
    await expect(title).toHaveValue(originalName);
    await title.fill(updatedName);
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText("Draft saved", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel" }).click();

    const updatedCard = page.getByRole("link", { name: `Open ${updatedName}`, exact: true });
    await expect(updatedCard).toHaveCount(1);
    const response = await page.request.get(`${API_URL}/events/${event.id}`, {
      headers: authHeaders(session),
    });
    expect(response.status()).toBe(200);
    expect((await response.json()).name).toBe(updatedName);
  } finally {
    if (event) await discardDraft(page, session, event.id);
  }
});

test("TC-ORG-006 a failed draft save keeps the saved title on the dashboard", async ({
  page,
  sharedSessions,
}) => {
  const session = await sharedSessions("event_organiser");
  const originalName = uniqueName("TC-ORG-006 draft");
  const unsavedName = `${originalName} unsaved`;
  let event;
  try {
    event = await createDraft(page, session, originalName);
    await seedSession(page, session);
    const eventPath = `${new URL(API_URL).pathname}/events/${event.id}`;
    await page.route((url) => new URL(url).pathname === eventPath, (route) => {
      if (route.request().method() === "PATCH") {
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Service unavailable" }),
        });
      }
      return route.continue();
    });
    await page.goto(`/events/new?id=${event.id}`);
    const title = page.getByLabel("Event title");
    await expect(title).toHaveValue(originalName);
    await title.fill(unsavedName);
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByRole("alert")).toContainText("Service unavailable");
    await expect(page.getByText("Draft saved", { exact: true })).toHaveCount(0);

    const response = await page.request.get(`${API_URL}/events/${event.id}`, {
      headers: authHeaders(session),
    });
    expect(response.status()).toBe(200);
    expect((await response.json()).name).toBe(originalName);

    await page.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Leave page" }).click();
    await expect(page.getByRole("link", { name: `Open ${originalName}`, exact: true })).toHaveCount(1);
    await expect(page.getByText(unsavedName, { exact: true })).toHaveCount(0);
  } finally {
    if (event) await discardDraft(page, session, event.id);
  }
});
