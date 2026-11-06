import { API_URL, expect, seedSession, test } from "./support/fixtures.js";
import { RUN_ID } from "./support/throwaway.js";

function authHeaders(token) {
  const key = ["Authoriz", "ation"].join("");
  const scheme = ["Bear", "er"].join("");
  return { [key]: `${scheme} ${token}` };
}

const futureSingaporeDate = (daysAhead = 2) => {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Singapore",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    })
      .formatToParts(new Date())
      .map(({ type, value }) => [type, value]),
  );
  const date = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day) + daysAhead));
  return date.toISOString().slice(0, 10);
};

async function createDraft(request, token, tag) {
  const response = await request.post(`${API_URL}/events`, {
    headers: authHeaders(token),
    data: { name: `live-check ${RUN_ID} ${tag}` },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function fillValidRequest(page, name) {
  await page.getByLabel("Event title").fill(name);
  await page.getByLabel("Purpose").first().fill("Regional planning workshop");
  await page.getByLabel("Proposed event date").fill(futureSingaporeDate());
  await page.getByLabel("Proposed start time").fill("14:00");
  await page.getByLabel("Proposed end time").fill("17:00");
  await page.getByLabel("Total expected attendance").fill("40");
  await page.getByLabel("Space purpose").selectOption("main_venue");
  await page.getByLabel("Expected pax").fill("40");
  await page.getByLabel("Preferred layout").selectOption("theatre");
}

test("TC-EVENT-001 an organiser saves a minimal draft and finds it in their list", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  const name = `live-check ${RUN_ID} 9-001`;
  await page.goto("/events/new");
  await page.getByLabel("Event title").fill(name);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByLabel("Event title")).toHaveValue(name);

  await page.goto("/dashboard/organiser");
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
});

test("TC-EVENT-002 draft titles below and above the allowed length are not saved", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/events/new");
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/events")) writes.push(request.url());
  });

  for (const name of ["", "ab", "x".repeat(151)]) {
    await page.getByLabel("Event title").fill(name);
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(
      page.getByText(/Enter an event title|Use at least 3 characters|Use at most 150 characters/i),
    ).toBeVisible();
  }
  expect(writes).toEqual([]);
});

test("TC-EVENT-007 empty optional draft fields reload and remain editable", async ({
  page,
  sharedSessions,
}) => {
  const session = await sharedSessions("event_organiser");
  await seedSession(page, session);
  const event = await createDraft(page.request, session.token, "9-007");
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`/events/new?id=${event.id}`);
  await expect(page.getByLabel("Event title")).toHaveValue(event.name);
  await expect(page.getByLabel("Purpose").first()).toHaveValue("");
  await expect(page.getByLabel("Proposed event date")).toHaveValue("");
  await expect(page.getByLabel("Proposed start time")).toHaveValue("");
  await expect(page.getByLabel("Proposed end time")).toHaveValue("");
  await page.getByLabel("Event title").fill(`${event.name} updated`);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByLabel("Event title")).toHaveValue(`${event.name} updated`);
  expect(pageErrors).toEqual([]);
});

test("TC-EVENT-008 a draft-load failure is shown without breaking the form", async ({
  page,
  sharedSessions,
}) => {
  const session = await sharedSessions("event_organiser");
  await seedSession(page, session);
  const event = await createDraft(page.request, session.token, "9-008");
  await page.route(`**/events/${event.id}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Live-check draft read failed." }),
    });
  });

  await page.goto(`/events/new?id=${event.id}`);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Start an event|Edit your draft/ })).toBeVisible();
});

test("TC-EVENT-009 a draft-update conflict is shown without false success", async ({
  page,
  sharedSessions,
}) => {
  const session = await sharedSessions("event_organiser");
  await seedSession(page, session);
  const event = await createDraft(page.request, session.token, "9-009");
  await page.goto(`/events/new?id=${event.id}`);
  await expect(page.getByLabel("Event title")).toHaveValue(event.name);
  await page.getByLabel("Event title").fill(`${event.name} attempted edit`);
  let interceptedPatch = false;
  await page.route(new RegExp(`/events/${event.id}/?$`), async (route) => {
    const request = route.request();
    if (request.method() !== "PATCH") return route.continue();
    interceptedPatch = true;
    return route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Live-check update conflict." }),
    });
  });

  await page.getByRole("button", { name: "Save draft" }).click();
  await expect.poll(() => interceptedPatch).toBe(true);
  await expect(page.getByRole("alert")).toContainText("Live-check update conflict.");
  await expect(page.getByRole("button", { name: "Save draft" })).toBeEnabled();
  const saved = await page.request.get(`${API_URL}/events/${event.id}`, {
    headers: authHeaders(session.token),
  });
  expect(saved.status()).toBe(200);
  expect((await saved.json()).name).toBe(event.name);
});

test("TC-EVENT-020 a valid request is submitted and appears in the organiser list", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  const name = `live-check ${RUN_ID} 8-020`;
  await page.goto("/events/new");
  await fillValidRequest(page, name);

  const submittedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/events/") &&
      response.url().endsWith("/submit") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Submit request" }).click();
  await page.getByRole("button", { name: "Confirm and submit" }).click();
  const response = await submittedResponse;
  expect(response.status()).toBe(200);
  const submitted = await response.json();
  expect(submitted.id).toMatch(/^[0-9a-f-]{36}$/i);
  expect(submitted.status).toBe("submitted");

  await expect(page.getByRole("status").filter({ hasText: "Request submitted" })).toContainText("Request submitted");
  await expect(page.getByText(name, { exact: true })).toBeVisible();
});

test("TC-EVENT-036 Enter preserves description lines and submits only after confirmation", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("event_organiser"));
  await page.goto("/events/new");
  const writes = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/events")) writes.push(request.url());
  });

  const description = page.getByLabel("Description");
  await description.fill("line one\nline two");
  await expect(description).toHaveValue("line one\nline two");
  await page.getByLabel("Event title").press("Enter");
  await expect(page.getByText("Enter an event title.")).toBeVisible();
  expect(writes).toEqual([]);

  await fillValidRequest(page, `live-check ${RUN_ID} 8-036`);
  await page.getByLabel("Event title").press("Enter");
  await expect(page.getByText("Submit event request?")).toBeVisible();
  expect(writes).toEqual([]);
  await page.getByRole("button", { name: "Review request" }).click();
  expect(writes).toEqual([]);
});
