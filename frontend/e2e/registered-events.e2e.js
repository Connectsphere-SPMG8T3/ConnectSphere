// Cases: docs/test-cases/events.md (SCRUM-56).
import { expect, seedSession, test } from "./support/fixtures.js";

test("TC-REG-008 the attendee My events view reflects the current registrations API response", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("attendee"));
  const registrationsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/registrations/me"),
  );
  await page.goto("/dashboard/attendee?tab=events");

  const response = await registrationsResponse;
  expect(response.status()).toBe(200);
  const { registrations } = await response.json();
  await expect(page.getByRole("heading", { name: "My events" })).toBeVisible();

  if (registrations.length === 0) {
    await expect(page.getByText("No registered events yet")).toBeVisible();
    return;
  }

  const labels = { registered: "Registered", waitlisted: "Waitlisted" };
  const formatRange = (event) => {
    const date = (value) => new Intl.DateTimeFormat("en-SG", {
      day: "numeric",
      month: "short",
      year: "numeric",
      timeZone: event.event_timezone,
    }).format(new Date(value));
    const time = (value) => new Intl.DateTimeFormat("en-SG", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: event.event_timezone,
    }).format(new Date(value)).replace(/\s/g, "");
    const startsAt = new Date(event.starts_at);
    const endsAt = new Date(event.ends_at);
    const startDate = date(startsAt);
    const endDate = date(endsAt);
    const startTime = time(startsAt);
    const endTime = time(endsAt);
    return startDate === endDate
      ? `${startDate} ${startTime} - ${endTime}`
      : `${startDate} ${startTime} - ${endDate} ${endTime}`;
  };

  for (const registration of registrations) {
    const { event } = registration;
    const groupName = Date.parse(event.ends_at) <= Date.now() ? "past" : "upcoming";
    const group = page.locator(`[data-testid="${groupName}-registrations"]`);
    const card = group.locator(`[data-event-row="${event.id}"]`);
    await expect(card).toBeVisible();
    await expect(card).toContainText(event.name);
    await expect(card).toContainText(formatRange(event));
    await expect(card).toContainText(labels[registration.status]);
    await expect(card).not.toContainText("confirmed");
    for (const venue of event.venues) {
      await expect(card).toContainText(venue.name);
    }
  }

  const firstRegistration = registrations[0];
  const filter = Date.parse(firstRegistration.event.ends_at) <= Date.now() ? "Past" : "Upcoming";
  await page.getByRole("button", { name: filter, exact: true }).click();
  await expect(
    page.getByRole("link", { name: `Open ${firstRegistration.event.name}` }),
  ).toBeVisible();
  await page.getByRole("link", { name: `Open ${firstRegistration.event.name}` }).click();
  await expect(page).toHaveURL(`/dashboard/attendee/events/${firstRegistration.event.id}`);
  await expect(page.getByRole("heading", { name: firstRegistration.event.name })).toBeVisible();
  await expect(page.getByRole("heading", { name: "About this event" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Venue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your registration" })).toBeVisible();
  await expect(page.locator('[data-testid="event-details-page"] > header')).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Back to My events" })).toHaveCount(0);
  const navigation = page.locator("aside nav");
  await expect(navigation.getByRole("link", { name: "Overview" })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "My events" })).toBeVisible();
});

test("TC-REG-011 events are grouped by whether their end time has passed", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("attendee"));
  const registrationsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/registrations/me"),
  );
  await page.goto("/dashboard/attendee?tab=events");

  const response = await registrationsResponse;
  expect(response.status()).toBe(200);
  const { registrations } = await response.json();
  const now = Date.now();
  const past = registrations.filter(({ event }) => Date.parse(event.ends_at) <= now);
  const upcoming = registrations.filter(({ event }) => Date.parse(event.ends_at) > now);
  const inProgress = registrations.filter(({ event }) =>
    Date.parse(event.starts_at) <= now && Date.parse(event.ends_at) > now,
  );

  test.skip(!past.length || !upcoming.length, "Needs both past and upcoming registrations.");

  const idsIn = async (group) =>
    page.locator(`[data-testid="${group}-registrations"] [data-event-row]`)
      .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-event-row")));
  const idsByStart = (items) =>
    items
      .slice()
      .sort((left, right) => Date.parse(left.event.starts_at) - Date.parse(right.event.starts_at))
      .map(({ event }) => event.id);

  expect(await idsIn("past")).toEqual(idsByStart(past));
  expect(await idsIn("upcoming")).toEqual(idsByStart(upcoming));
  test.skip(!inProgress.length, "No in-progress registration is available to verify that it remains Upcoming.");
});

test("TC-REG-014 My events filters, sorting and registered-event details", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("attendee"));
  const registrationsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/registrations/me"),
  );
  await page.goto("/dashboard/attendee?tab=events");

  const response = await registrationsResponse;
  expect(response.status()).toBe(200);
  const { registrations } = await response.json();
  test.skip(registrations.length < 2, "Needs multiple current registrations to exercise filters and sorting.");
  const now = Date.now();
  const registrationsById = new Map(registrations.map(({ event }) => [event.id, event]));
  const idsIn = async (selector = "[data-event-row]") =>
    page.locator(selector).evaluateAll((rows) => rows.map((row) => row.getAttribute("data-event-row")));
  const eventIds = (items) => items.map(({ event }) => event.id);
  const expectSameIds = async (actual, expected) => {
    expect([...actual].sort()).toEqual([...expected].sort());
  };
  const past = registrations.filter(({ event }) => Date.parse(event.ends_at) <= now);
  const upcoming = registrations.filter(({ event }) => Date.parse(event.ends_at) > now);

  const search = page.getByLabel("Search my events");
  const query = registrations[0].event.name;
  await search.fill(query);
  const matches = registrations.filter(({ event }) =>
    event.name.toLocaleLowerCase("en-SG").includes(query.toLocaleLowerCase("en-SG")),
  );
  await expectSameIds(await idsIn(), eventIds(matches));
  await search.fill("");

  await page.getByRole("button", { name: "Filter registrations by status" }).click();
  const registeredFilter = page.getByLabel("Registered", { exact: true });
  await registeredFilter.check();
  await expectSameIds(
    await idsIn(),
    eventIds(registrations.filter(({ status }) => status === "registered")),
  );
  await registeredFilter.uncheck();
  await page.getByLabel("Waitlisted", { exact: true }).check();
  await expectSameIds(
    await idsIn(),
    eventIds(registrations.filter(({ status }) => status === "waitlisted")),
  );
  await page.getByRole("button", { name: "Clear my event filters" }).click();

  await page.getByRole("button", { name: "Past", exact: true }).click();
  await expectSameIds(await idsIn(), eventIds(past));
  await page.getByRole("button", { name: "Upcoming", exact: true }).click();
  await expectSameIds(await idsIn(), eventIds(upcoming));
  await page.getByRole("button", { name: "All", exact: true }).click();

  const sortButton = page.getByRole("button", { name: "Sort my events by" });
  const selectSort = async (label) => {
    await sortButton.click();
    await page.getByRole("option", { name: label, exact: true }).click();
  };
  const expectGroupSorted = async (group, field, direction) => {
    const groupRegistrations = registrations.filter(({ event }) =>
      group === "past" ? Date.parse(event.ends_at) <= now : Date.parse(event.ends_at) > now,
    );
    const expected = groupRegistrations
      .slice()
      .sort((left, right) => {
        const comparison = field === "name"
          ? left.event.name.localeCompare(right.event.name, "en-SG")
          : Date.parse(left.event.starts_at) - Date.parse(right.event.starts_at);
        return direction === "asc" ? comparison : -comparison;
      })
      .map(({ event }) => event.id);
    const actual = await idsIn(`[data-testid="${group}-registrations"] [data-event-row]`);
    expect(actual).toEqual(expected);
  };

  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "date", "asc");
  await selectSort("Event name");
  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "name", "asc");
  await page.getByRole("button", { name: /Toggle sort direction/ }).click();
  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "name", "desc");
  await selectSort("Event date");
  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "date", "desc");
  await page.getByRole("button", { name: /Toggle sort direction/ }).click();
  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "date", "asc");
  await page.getByRole("button", { name: "Clear my event filters" }).click();
  for (const group of ["past", "upcoming"]) await expectGroupSorted(group, "date", "asc");

  const eventId = registrations[0].event.id;
  const eventName = registrationsById.get(eventId).name;
  await Promise.all([
    page.waitForURL(`**/dashboard/attendee/events/${eventId}`),
    page.locator(`[data-event-row="${eventId}"]`).click(),
  ]);
  await expect(page.getByRole("heading", { name: eventName, exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your registration" })).toBeVisible();
});

test("TC-REG-013 attendee overview counts match current registrations and the public directory", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("attendee"));
  const registrationsResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/registrations/me"),
  );
  const directoryResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/public/events"),
  );
  await page.goto("/dashboard/attendee?tab=overview");

  const [registrationsResult, directoryResult] = await Promise.all([
    registrationsResponse,
    directoryResponse,
  ]);
  expect(registrationsResult.status()).toBe(200);
  expect(directoryResult.status()).toBe(200);
  const { registrations } = await registrationsResult.json();
  const { events } = await directoryResult.json();
  const now = Date.now();
  const distinctCount = (items) => new Set(items.map(({ event }) => event.id)).size;
  const expectedUpcoming = distinctCount(
    registrations.filter(({ status, event }) =>
      ["registered", "waitlisted"].includes(status) && Date.parse(event.ends_at) > now,
    ),
  );
  const expectedPast = distinctCount(
    registrations.filter(({ status, event }) =>
      status === "registered" && Date.parse(event.ends_at) <= now,
    ),
  );
  const expectedOpen = events.filter(({ availability }) => availability === "open").length;

  await expect(page.getByTestId("summary-upcoming-registrations").locator(".text-5xl"))
    .toHaveText(String(expectedUpcoming));
  await expect(page.getByTestId("summary-open-events").locator(".text-5xl"))
    .toHaveText(String(expectedOpen));
  await expect(page.getByTestId("summary-past-registrations").locator(".text-5xl"))
    .toHaveText(String(expectedPast));
});

test("TC-REG-015 Explore events uses public directory data with search and sorting", async ({
  page,
  sharedSessions,
}) => {
  await seedSession(page, await sharedSessions("attendee"));
  const directoryResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/public/events"),
  );
  await page.goto("/dashboard/attendee?tab=explore");

  const response = await directoryResponse;
  expect(response.status()).toBe(200);
  const { events } = await response.json();
  await expect(page.getByRole("heading", { name: "Explore events" })).toBeVisible();

  if (events.length === 0) {
    await expect(page.getByText("No public events yet")).toBeVisible();
    return;
  }

  const firstEvent = events[0];
  const card = page.locator("article").filter({
    has: page.getByRole("heading", { name: firstEvent.name, exact: true }),
  });
  await expect(card).toContainText(firstEvent.name);
  await expect(card).not.toContainText("confirmed");
  await expect(card).toContainText(firstEvent.venues.map(({ name }) => name).join(" · ") || "Venue details to be announced");
  await expect(card.getByRole("link", { name: "View event" })).toHaveAttribute(
    "href",
    `/attendee/events/${firstEvent.id}`,
  );

  const search = page.getByLabel("Search public events");
  await search.fill(firstEvent.name);
  const matchingEvents = events.filter(({ name }) =>
    name.toLocaleLowerCase("en-SG").includes(firstEvent.name.toLocaleLowerCase("en-SG")),
  );
  const sortBy = page.getByLabel("Sort public events by");
  await sortBy.selectOption("name");
  await expect(page.locator("article h3")).toHaveText(matchingEvents
    .slice()
    .sort((left, right) => left.name.localeCompare(right.name, "en-SG"))
    .map(({ name }) => name));

  await search.fill("");
  await sortBy.selectOption("date");
  const eventsByDate = events
    .slice()
    .sort((left, right) => Date.parse(left.starts_at) - Date.parse(right.starts_at));
  await expect(page.locator("article h3")).toHaveText(eventsByDate.map(({ name }) => name));

  if (eventsByDate.length > 1) {
    await page.getByRole("button", { name: /Toggle sort direction/ }).click();
    await expect(page.locator("article h3")).toHaveText(
      eventsByDate.slice().reverse().map(({ name }) => name),
    );
  }

  const registrationStatusResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith("/registrations/me"),
  );
  await card.getByRole("link", { name: "View event" }).click();
  await expect(page).toHaveURL(`/attendee/events/${firstEvent.id}`);
  const registrationStatusResult = await registrationStatusResponse;
  expect(registrationStatusResult.status()).toBe(200);
  const { registrations: currentRegistrations } = await registrationStatusResult.json();
  if (currentRegistrations.some(({ event, status }) =>
    event.id === firstEvent.id && status === "registered",
  )) {
    const registeredButton = page.getByRole("button", { name: "Registered", exact: true });
    await expect(registeredButton).toBeVisible();
    await expect(registeredButton).toBeDisabled();
  }
  const eventDetail = page.getByTestId("event-details-page");
  await expect(eventDetail.locator("> header")).toHaveCount(0);
  await expect(eventDetail.getByRole("link", { name: "ConnectSphere events" })).toHaveCount(0);
  await expect(eventDetail.getByRole("link", { name: "All events", exact: true })).toHaveCount(0);
  await expect(page.locator("aside nav").getByRole("link", { name: "Explore events" })).toBeVisible();
});
