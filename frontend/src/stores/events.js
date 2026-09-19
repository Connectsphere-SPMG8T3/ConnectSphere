import { defineStore } from "pinia";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

import { FACILITIES, LAYOUTS, toSingaporeIso } from "@/stores/venues";

export { FACILITIES, LAYOUTS };

export function emptyEvent() {
  return {
    name: "",
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

export function eventToPayload(event) {
  const payload = {
    name: (event.name ?? "").trim(),
    purpose: (event.purpose ?? "").trim() || undefined,
    description: (event.description ?? "").trim() || undefined,
    expected_attendance: event.expectedAttendance === "" ? undefined : Number(event.expectedAttendance),
    layout_preference: event.layoutPreference || undefined,
    facilities_required: [...event.facilitiesRequired],
    accessibility_needs: (event.accessibilityNeeds ?? "").trim() || undefined,
    preliminary_equipment_needs: (event.preliminaryEquipmentNeeds ?? "").trim() || undefined,
    registration_enabled: event.registrationEnabled,
  };
  if (event.date && event.startTime) payload.starts_at = toSingaporeIso(event.date, event.startTime);
  if (event.date && event.endTime) payload.ends_at = toSingaporeIso(event.date, event.endTime);
  if (event.registrationCapacity !== "") payload.registration_capacity = Number(event.registrationCapacity);
  if (event.registrationOpensAt) payload.registration_opens_at = toSingaporeIso(event.date, event.registrationOpensAt);
  if (event.registrationClosesAt) payload.registration_closes_at = toSingaporeIso(event.date, event.registrationClosesAt);
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined));
}

function fromResponse(event) {
  const defaults = emptyEvent();
  return {
    ...defaults,
    ...event,
    name: event.name ?? defaults.name,
    purpose: event.purpose ?? defaults.purpose,
    description: event.description ?? defaults.description,
    date: event.starts_at?.slice(0, 10) ?? "",
    startTime: event.starts_at?.slice(11, 16) ?? "",
    endTime: event.ends_at?.slice(11, 16) ?? "",
    expectedAttendance: event.expected_attendance ?? "",
    layoutPreference: event.layout_preference ?? "",
    facilitiesRequired: event.facilities_required ?? [],
    accessibilityNeeds: event.accessibility_needs ?? defaults.accessibilityNeeds,
    preliminaryEquipmentNeeds: event.preliminary_equipment_needs ?? defaults.preliminaryEquipmentNeeds,
    registrationEnabled: event.registration_enabled ?? defaults.registrationEnabled,
    registrationCapacity: event.registration_capacity ?? "",
    registrationOpensAt: event.registration_opens_at?.slice(11, 16) ?? "",
    registrationClosesAt: event.registration_closes_at?.slice(11, 16) ?? "",
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

    async saveDraft(event) {
      return this.save((token) => eventsApi.create(eventToPayload(event), token));
    },

    async updateDraft(eventId, event) {
      return this.save((token) => eventsApi.update(eventId, eventToPayload(event), token));
    },

    async submit(eventId, event) {
      return this.save((token) => eventsApi.submit(eventId, eventToPayload(event), token));
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