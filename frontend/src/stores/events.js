import { defineStore } from "pinia";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

import { DEFAULT_EVENT_TIMEZONE, fromZonedDateTime, toZonedIso } from "@/features/events/timezones";
// `stores/venues.js` moved to `features/venues/venueSearchStore.js` during
// SCRUM-70 while SCRUM-8 was in flight; the two merged without this import
// being repointed, which broke `npm run build` (DEFECTS D9).
import { FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

export { FACILITIES, LAYOUTS };

export function emptySpace() {
  return {
    id: null,
    version: 1,
    label: "",
    expectedPax: "",
    layoutPreference: "",
    facilitiesRequired: [],
    useEventSchedule: true,
    startsAt: "",
    endsAt: "",
  };
}

function spaceDateTimeToIso(value, eventTimezone) {
  if (!value) return null;
  const [date, time] = value.split("T");
  return date && time ? toZonedIso(date, time, eventTimezone) : null;
}

export function spaceToPayload(space, eventTimezone = DEFAULT_EVENT_TIMEZONE) {
  const inheritsEventSchedule = space.useEventSchedule !== false;
  return {
    label: space.label.trim(),
    expected_pax: Number(space.expectedPax),
    layout_preference: space.layoutPreference,
    facilities_required: [...(space.facilitiesRequired ?? [])],
    starts_at: inheritsEventSchedule ? null : spaceDateTimeToIso(space.startsAt, eventTimezone),
    ends_at: inheritsEventSchedule ? null : spaceDateTimeToIso(space.endsAt, eventTimezone),
  };
}

function spaceFromResponse(space, eventTimezone) {
  const defaults = emptySpace();
  const startsAt = fromZonedDateTime(space.starts_at, eventTimezone);
  const endsAt = fromZonedDateTime(space.ends_at, eventTimezone);
  return {
    ...defaults,
    ...space,
    expectedPax: space.expected_pax ?? "",
    layoutPreference: space.layout_preference ?? "",
    facilitiesRequired: [...(space.facilities_required ?? [])],
    useEventSchedule: !space.starts_at && !space.ends_at,
    startsAt: startsAt.date && startsAt.time ? `${startsAt.date}T${startsAt.time}` : "",
    endsAt: endsAt.date && endsAt.time ? `${endsAt.date}T${endsAt.time}` : "",
  };
}

export function emptyEvent() {
  return {
    spaces: [],
    name: "",
    eventTimezone: DEFAULT_EVENT_TIMEZONE,
    purpose: "",
    description: "",
    date: "",
    startTime: "",
    endTime: "",
    expectedAttendance: "",
    layoutPreference: "",
    facilitiesRequired: [],
    accessibilityNeeds: "",
    preliminaryEquipmentNeeds: "",
    registrationEnabled: false,
    registrationCapacity: "",
    registrationOpensAt: "",
    registrationClosesAt: "",
    withdrawalClosesAt: "",
    reRegistrationAllowed: true,
    waitlistEnabled: true,
  };
}

// `clearing`: the payload edits an existing event, so a field the organiser
// emptied is sent as null (the API only changes fields present in the body).
// A new event just leaves it out. The start/end pair is never cleared here:
// the database needs both or neither, and submission requires them anyway.
export function eventToPayload(event, { clearing = false } = {}) {
  const blank = clearing ? null : undefined;
  const payload = {
    name: (event.name ?? "").trim(),
    event_timezone: event.eventTimezone || DEFAULT_EVENT_TIMEZONE,
    purpose: (event.purpose ?? "").trim() || blank,
    description: (event.description ?? "").trim() || blank,
    expected_attendance: event.expectedAttendance === "" || event.expectedAttendance == null ? blank : Number(event.expectedAttendance),
    accessibility_needs: (event.accessibilityNeeds ?? "").trim() || blank,
    preliminary_equipment_needs: (event.preliminaryEquipmentNeeds ?? "").trim() || blank,
    registration_enabled: event.registrationEnabled,
    re_registration_allowed: event.reRegistrationAllowed,
    waitlist_enabled: event.waitlistEnabled,
    registration_capacity: blank,
    registration_opens_at: blank,
    registration_closes_at: blank,
    withdrawal_closes_at: blank,
  };
  if (event.date && event.startTime) payload.starts_at = toZonedIso(event.date, event.startTime, payload.event_timezone);
  if (event.date && event.endTime) payload.ends_at = toZonedIso(event.date, event.endTime, payload.event_timezone);
  if (event.registrationCapacity !== "" && event.registrationCapacity != null) payload.registration_capacity = Number(event.registrationCapacity);
  if (event.registrationOpensAt) {
    const [registrationOpensDate, registrationOpensTime] = event.registrationOpensAt.split("T");
    if (registrationOpensDate && registrationOpensTime) {
      payload.registration_opens_at = toZonedIso(registrationOpensDate, registrationOpensTime, payload.event_timezone);
    }
  }
  if (event.registrationClosesAt) {
    const [registrationClosesDate, registrationClosesTime] = event.registrationClosesAt.split("T");
    if (registrationClosesDate && registrationClosesTime) {
      payload.registration_closes_at = toZonedIso(registrationClosesDate, registrationClosesTime, payload.event_timezone);
    }
  }
  if (event.withdrawalClosesAt) {
    const [withdrawalDate, withdrawalTime] = event.withdrawalClosesAt.split("T");
    if (withdrawalDate && withdrawalTime) {
      payload.withdrawal_closes_at = toZonedIso(withdrawalDate, withdrawalTime, payload.event_timezone);
    }
  }
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined));
}

function fromResponse(event) {
  const defaults = emptyEvent();
  const eventTimezone = event.event_timezone || DEFAULT_EVENT_TIMEZONE;
  const startsAt = fromZonedDateTime(event.starts_at, eventTimezone);
  const endsAt = fromZonedDateTime(event.ends_at, eventTimezone);
  const registrationOpensAt = fromZonedDateTime(event.registration_opens_at, eventTimezone);
  const registrationClosesAt = fromZonedDateTime(event.registration_closes_at, eventTimezone);
  const withdrawalClosesAt = fromZonedDateTime(event.withdrawal_closes_at, eventTimezone);
  return {
    ...defaults,
    ...event,
    spaces: (event.spaces ?? []).map((space) => spaceFromResponse(space, eventTimezone)),
    name: event.name ?? defaults.name,
    eventTimezone,
    purpose: event.purpose ?? defaults.purpose,
    description: event.description ?? defaults.description,
    coordinatorId: event.coordinator_id ?? null,
    date: startsAt.date,
    startTime: startsAt.time,
    endTime: endsAt.time,
    expectedAttendance: event.expected_attendance ?? "",
    layoutPreference: event.layout_preference ?? "",
    facilitiesRequired: event.facilities_required ?? [],
    accessibilityNeeds: event.accessibility_needs ?? defaults.accessibilityNeeds,
    preliminaryEquipmentNeeds: event.preliminary_equipment_needs ?? defaults.preliminaryEquipmentNeeds,
    registrationEnabled: event.registration_enabled ?? defaults.registrationEnabled,
    registrationCapacity: event.registration_capacity ?? "",
    registrationOpensAt: registrationOpensAt.date && registrationOpensAt.time ? `${registrationOpensAt.date}T${registrationOpensAt.time}` : "",
    registrationClosesAt: registrationClosesAt.date && registrationClosesAt.time ? `${registrationClosesAt.date}T${registrationClosesAt.time}` : "",
    withdrawalClosesAt: withdrawalClosesAt.date && withdrawalClosesAt.time ? `${withdrawalClosesAt.date}T${withdrawalClosesAt.time}` : "",
    reRegistrationAllowed: event.re_registration_allowed ?? defaults.reRegistrationAllowed,
    waitlistEnabled: event.waitlist_enabled ?? defaults.waitlistEnabled,
  };
}

async function withSpaceRequest(store, operation) {
  const authStore = useAuthStore();
  store.error = null;
  try {
    return await authStore.withSession(operation);
  } catch (error) {
    store.error = error.message;
    throw error;
  }
}

export const useEventsStore = defineStore("events", {
  state: () => ({ events: [], isLoading: false, isSaving: false, error: null }),

  getters: {
    drafts: (state) => state.events.filter((event) => event.status === "draft"),
    requests: (state) => state.events.filter((event) => event.status !== "draft"),
  },

  actions: {
    async createSpace(eventId, payload) {
      return withSpaceRequest(this, (token) => eventsApi.createSpace(eventId, payload, token));
    },

    async updateSpace(eventId, spaceId, payload) {
      return withSpaceRequest(this, (token) => eventsApi.updateSpace(eventId, spaceId, payload, token));
    },

    async removeSpace(eventId, spaceId) {
      return withSpaceRequest(this, (token) => eventsApi.removeSpace(eventId, spaceId, token));
    },

    async load() {
      const authStore = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        this.events = (await authStore.withSession((token) => eventsApi.list(token))).map(fromResponse);
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isLoading = false;
      }
    },

    // Story 84: errors go to the caller (the dialog shows them), not the page alert.
    async requestCancellation(eventId, reason) {
      const authStore = useAuthStore();
      const request = await authStore.withSession((token) => eventsApi.requestCancellation(eventId, reason, token));
      await this.get(eventId);
      return request;
    },

    // Story 32: as requestCancellation, errors go to the dialog.
    async requestChange(eventId, body) {
      const authStore = useAuthStore();
      const request = await authStore.withSession((token) => eventsApi.requestChange(eventId, body, token));
      await this.get(eventId);
      return request;
    },

    async get(eventId) {
      const authStore = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        const event = fromResponse(await authStore.withSession((token) => eventsApi.get(eventId, token)));
        const index = this.events.findIndex((storedEvent) => storedEvent.id === event.id);
        if (index === -1) this.events.push(event);
        else this.events[index] = event;
        return event;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isLoading = false;
      }
    },

    async saveDraft(event) {
      return this.save((token) => eventsApi.create(eventToPayload(event), token));
    },

    async clone(eventId) {
      return this.save((token) => eventsApi.clone(eventId, token));
    },

    async updateDraft(eventId, event) {
      return this.save((token) => eventsApi.update(eventId, eventToPayload(event, { clearing: true }), token));
    },

    // Story 9 AC6 (D81): the API deletes the draft only for its owner and only while
    // it is still a draft; anything else comes back as an error to show the organiser.
    async discard(eventId) {
      const authStore = useAuthStore();
      this.isSaving = true;
      this.error = null;
      try {
        await authStore.withSession((token) => eventsApi.remove(eventId, token));
        this.events = this.events.filter((event) => event.id !== eventId);
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isSaving = false;
      }
    },

    async submit(eventId, event) {
      return this.save((token) => eventsApi.submit(eventId, eventToPayload(event, { clearing: true }), token));
    },

    // SCRUM-33: send a returned request back to its coordinator with the form's
    // edits and the organiser's note, in one request (like submit).
    async resubmit(eventId, event, note) {
      return this.save((token) =>
        eventsApi.resubmit(eventId, { ...eventToPayload(event, { clearing: true }), resubmission_note: note.trim() }, token),
      );
    },

    async createAndSubmit(event) {
      const draft = await this.saveDraft(event);
      return this.submit(draft.id, event);
    },

    async save(operation) {
      const authStore = useAuthStore();
      this.isSaving = true;
      this.error = null;
      try {
        const result = await authStore.withSession((token) => operation(token));
        const normalized = fromResponse(result);
        const index = this.events.findIndex((event) => event.id === normalized.id);
        if (index === -1) this.events.push(normalized);
        else this.events[index] = normalized;
        return normalized;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isSaving = false;
      }
    },
  },
});