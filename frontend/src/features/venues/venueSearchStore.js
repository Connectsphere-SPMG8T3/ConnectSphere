import { defineStore } from "pinia";

import { toSingaporeIso } from "@/features/venues/singaporeTime";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Controlled lists (REQUIREMENTS §6.8, [Team decision]); values mirror the
// Postgres enums, labels are what the coordinator reads.
export const LAYOUTS = [
  { value: "theatre", label: "Theatre" },
  { value: "classroom", label: "Classroom" },
  { value: "boardroom", label: "Boardroom" },
  { value: "banquet", label: "Banquet" },
  { value: "u_shape", label: "U-shape" },
  { value: "reception", label: "Reception" },
];

export const FACILITIES = [
  { value: "projector", label: "Projector" },
  { value: "sound_system", label: "Sound system" },
  { value: "microphone", label: "Microphone" },
  { value: "video_conferencing", label: "Video conferencing" },
  { value: "whiteboard", label: "Whiteboard" },
  { value: "stage", label: "Stage" },
  { value: "wifi", label: "Wi-Fi" },
  { value: "catering_space", label: "Catering space" },
];

export const ACCESSIBILITY_FEATURES = [
  { value: "wheelchair_access", label: "Wheelchair access" },
  { value: "step_free_entry", label: "Step-free entry" },
  { value: "accessible_toilet", label: "Accessible toilet" },
  { value: "hearing_loop", label: "Hearing loop" },
  { value: "lift_access", label: "Lift access" },
];

export function emptyCriteria() {
  return {
    date: "",
    startTime: "",
    endTime: "",
    minCapacity: "",
    location: "",
    layout: "",
    facilities: [],
    accessibility: [],
  };
}

// The store always asks for the excluded venues too and splits them locally,
// so the "Show excluded" toggle is instant instead of a second request.
export function criteriaToParams(criteria) {
  const params = { include_excluded: true };
  if (criteria.date && criteria.startTime && criteria.endTime) {
    params.starts_at = toSingaporeIso(criteria.date, criteria.startTime);
    params.ends_at = toSingaporeIso(criteria.date, criteria.endTime);
  }
  if (criteria.minCapacity !== "" && criteria.minCapacity !== null) {
    params.min_capacity = Number(criteria.minCapacity);
  }
  const location = criteria.location?.trim();
  if (location) params.location = location;
  if (criteria.layout) params.layout = criteria.layout;
  if (criteria.facilities?.length) params.facilities = [...criteria.facilities];
  if (criteria.accessibility?.length) params.accessibility = [...criteria.accessibility];
  return params;
}

function validate(criteria) {
  const errors = {};
  const anyTiming = criteria.date || criteria.startTime || criteria.endTime;
  if (anyTiming) {
    if (!criteria.date) errors.date = "Enter the event date.";
    if (!criteria.startTime) errors.startTime = "Enter the start time.";
    if (!criteria.endTime) errors.endTime = "Enter the end time.";
    if (criteria.startTime && criteria.endTime && criteria.endTime <= criteria.startTime) {
      errors.endTime = "End time must be after start time.";
    }
  }
  if (criteria.minCapacity !== "" && criteria.minCapacity !== null) {
    const capacity = Number(criteria.minCapacity);
    if (!Number.isInteger(capacity) || capacity < 1) {
      errors.minCapacity = "Expected attendance must be a whole number of at least 1.";
    }
  }
  return errors;
}

export const useVenuesStore = defineStore("venues", {
  state: () => ({
    criteria: emptyCriteria(),
    fieldErrors: {},
    results: [],
    includedCount: 0,
    excludedCount: 0,
    showExcluded: false,
    hasSearched: false,
    isLoading: false,
    error: null,
    selectedVenue: null,
    // The event (and space) the search is for (SCRUM-18); when set, the API
    // judges every result's suitability against it.
    context: null,
  }),

  getters: {
    includedResults: (state) => state.results.filter((result) => !result.excluded),
    excludedResults: (state) => state.results.filter((result) => result.excluded),
    hasPeriod: (state) => Boolean(state.criteria.date && state.criteria.startTime && state.criteria.endTime),
  },

  actions: {
    // True when the context changed, so results fetched for another event (or
    // none) are stale and the caller should search again.
    setContext(context) {
      const next = context?.eventId || context?.spaceId ? { eventId: context.eventId ?? null, spaceId: context.spaceId ?? null } : null;
      const changed = JSON.stringify(next) !== JSON.stringify(this.context);
      this.context = next;
      return changed;
    },

    resetCriteria() {
      this.criteria = emptyCriteria();
      this.fieldErrors = {};
    },

    async search() {
      this.fieldErrors = validate(this.criteria);
      if (Object.keys(this.fieldErrors).length > 0) return;

      const authStore = useAuthStore();
      const params = criteriaToParams(this.criteria);
      if (this.context?.eventId) params.event_id = this.context.eventId;
      if (this.context?.spaceId) params.space_id = this.context.spaceId;
      this.isLoading = true;
      this.error = null;
      try {
        const response = await authStore.withSession((token) => venuesApi.search(params, token));
        this.results = response.results;
        this.includedCount = response.included_count;
        this.excludedCount = response.excluded_count;
        this.hasSearched = true;
      } catch (err) {
        // Previous results stay on screen; the message explains why the
        // refresh failed.
        this.error = err.message;
      } finally {
        this.isLoading = false;
      }
    },

    async fetchVenue(venueId) {
      const authStore = useAuthStore();
      this.isLoading = true;
      this.error = null;
      this.selectedVenue = null;
      try {
        const venue = await authStore.withSession((token) => venuesApi.get(venueId, token));
        this.selectedVenue = venue;
        return venue;
      } catch (err) {
        this.error = err.message;
        throw err;
      } finally {
        this.isLoading = false;
      }
    },
  },
});
