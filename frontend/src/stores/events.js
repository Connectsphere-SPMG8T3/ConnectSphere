import { defineStore } from "pinia";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

import { DEFAULT_EVENT_TIMEZONE, fromZonedDateTime, toZonedIso } from "@/features/events/timezones";
// `stores/venues.js` moved to `features/venues/venueSearchStore.js` during
// SCRUM-70 while SCRUM-8 was in flight; the two merged without this import
// being repointed, which broke `npm run build` (DEFECTS D9).
import { FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

export { FACILITIES, LAYOUTS };

export function emptyEvent() {
  return {
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
    layout_preference: event.layoutPreference || blank,
    facilities_required: [...event.facilitiesRequired],
    accessibility_needs: (event.accessibilityNeeds ?? "").trim() || blank,
    preliminary_equipment_needs: (event.preliminaryEquipmentNeeds ?? "").trim() || blank,
    registration_enabled: event.registrationEnabled,
    registration_capacity: blank,
    registration_opens_at: blank,
    registration_closes_at: blank,
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
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined));
}

function fromResponse(event) {
  const defaults = emptyEvent();
  const eventTimezone = event.event_timezone || DEFAULT_EVENT_TIMEZONE;
  const startsAt = fromZonedDateTime(event.starts_at, eventTimezone);
  const endsAt = fromZonedDateTime(event.ends_at, eventTimezone);
  const registrationOpensAt = fromZonedDateTime(event.registration_opens_at, eventTimezone);
  const registrationClosesAt = fromZonedDateTime(event.registration_closes_at, eventTimezone);
  return {
    ...defaults,
    ...event,
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
  };
}

export const useEventsStore = defineStore("events", {
  state: () => ({ events: [], isLoading: false, isSaving: false, error: null }),

  getters: {
    drafts: (state) => state.events.filter((event) => event.status === "draft"),
    requests: (state) => state.events.filter((event) => event.status !== "draft"),
  },

  actions: {
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

    async updateDraft(eventId, event) {
      return this.save((token) => eventsApi.update(eventId, eventToPayload(event, { clearing: true }), token));
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