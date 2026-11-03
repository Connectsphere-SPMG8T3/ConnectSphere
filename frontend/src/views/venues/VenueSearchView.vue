<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import SectionHeading from "@/components/common/SectionHeading.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import RequestVenueModal from "@/components/venues/RequestVenueModal.vue";
import VenueCriteriaForm from "@/components/venues/VenueCriteriaForm.vue";
import VenueResultCard from "@/components/venues/VenueResultCard.vue";
import { showToast } from "@/composables/useToast";
import { criteriaFromEvent, criteriaFromSpace, describeConflict, venuePanelState } from "@/features/venues/bookingRequest";
import { useVenueBookingStore } from "@/features/venues/venueBookingStore";
import { useVenuesStore } from "@/features/venues/venueSearchStore";
import { sortVenueResults, VENUE_SORT_OPTIONS } from "@/features/venues/venueSort";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const venuesStore = useVenuesStore();
const sortKey = ref("name");
// Venues that fail a requirement stay in the list, greyed out after the matches,
// each with the reasons it was excluded. The sort orders the matches only.
const orderedResults = computed(() => [
  ...sortVenueResults(venuesStore.includedResults, sortKey.value),
  ...venuesStore.excludedResults,
]);
const bookingStore = useVenueBookingStore();
const authStore = useAuthStore();

// Opened from an event (`/venues?event=<id>`, SCRUM-19): the search is
// pre-filled from the event and each available venue can be requested for it.
const bookingEvent = ref(null);
const bookingSpace = ref(null);
const eventCriteria = ref(null);
const eventError = ref(null);
const requestedVenue = ref(null);

const panelState = computed(() => venuePanelState(bookingEvent.value, bookingSpace.value));

// Opened to replace an affected or Safety-rejected booking (`&replaces=<booking
// id>`, CR-95 AC4, D52): requests are offered only while that booking still
// waits for a replacement.
const REPLACEABLE_PANELS = ["affected", "safety-rejected"];
const replacesId = computed(() => (route.query.replaces ? String(route.query.replaces) : null));
const replacedBooking = computed(() => {
  const panel = panelState.value;
  return REPLACEABLE_PANELS.includes(panel.kind) && panel.canReplace && panel.booking.id === replacesId.value
    ? panel.booking : null;
});
const canRequest = computed(() => panelState.value.kind === "can-request" || Boolean(replacedBooking.value));
// A Confirmed or Safety-review event returns to Planning as the request is made (AC7).
const returnsToPlanning = computed(
  () => Boolean(replacedBooking.value) && bookingEvent.value.status !== "planning",
);

// A venue is only offered while the search checks the selected space's
// effective period; otherwise "Available" would describe a different interval.
const searchMatchesEvent = computed(() => {
  const wanted = eventCriteria.value;
  const current = venuesStore.criteria;
  return Boolean(
    wanted?.date &&
      current.date === wanted.date &&
      current.startTime === wanted.startTime &&
      current.endTime === wanted.endTime,
  );
});

const eventPeriod = computed(() => {
  const event = bookingEvent.value;
  const startsAt = bookingSpace.value?.starts_at ?? event?.starts_at;
  const endsAt = bookingSpace.value?.ends_at ?? event?.ends_at;
  if (!startsAt || !endsAt) return "";
  const format = new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: event.event_timezone || "Asia/Singapore",
  });
  return `${format.format(new Date(startsAt))} – ${format.format(new Date(endsAt))}`;
});

async function loadEventContext(eventId, spaceId) {
  eventError.value = null;
  bookingEvent.value = null;
  bookingSpace.value = null;
  eventCriteria.value = null;
  try {
    const event = await authStore.withSession((token) => eventsApi.get(eventId, token));
    bookingEvent.value = event;
    bookingSpace.value = event.spaces?.find((space) => space.id === spaceId) ?? null;
    const criteria = bookingSpace.value ? criteriaFromSpace(bookingSpace.value, event) : criteriaFromEvent(event);
    eventCriteria.value = { ...criteria, facilities: [...criteria.facilities] };
    venuesStore.criteria = criteria;
    venuesStore.fieldErrors = {};
    // The API judges each venue's suitability against this event or space (SCRUM-18).
    venuesStore.setContext({ eventId: event.id, spaceId: bookingSpace.value?.id ?? null });
  } catch (error) {
    eventError.value = error.message;
    venuesStore.setContext(null);
  }
  venuesStore.search();
}

// First visit lists the whole catalogue; coming back from a detail page keeps
// the previous search (the store outlives the view).
watch(
  () => [route.query.event, route.query.space],
  ([eventId, spaceId]) => {
    if (eventId) {
      loadEventContext(String(eventId), spaceId ? String(spaceId) : null);
    } else {
      bookingEvent.value = null;
      bookingSpace.value = null;
      eventCriteria.value = null;
      // Leaving an event drops its verdicts: results fetched for it are stale.
      const hadContext = venuesStore.setContext(null);
      if (hadContext || !venuesStore.hasSearched) venuesStore.search();
    }
  },
  { immediate: true },
);

const requestedSuitability = computed(
  () => venuesStore.results.find((result) => result.venue.id === requestedVenue.value?.id)?.suitability ?? null,
);

function handleReset() {
  venuesStore.resetCriteria();
  venuesStore.search();
}

function openRequest(venue) {
  bookingStore.error = null;
  requestedVenue.value = venue;
}

async function confirmRequest(note, acknowledgedWarnings = false) {
  try {
    const replaces = replacedBooking.value?.id ?? null;
    if (bookingSpace.value) {
      await bookingStore.requestForSpace(bookingSpace.value.id, requestedVenue.value.id, note, replaces, acknowledgedWarnings);
    } else {
      await bookingStore.request(bookingEvent.value.id, requestedVenue.value.id, note, replaces, acknowledgedWarnings);
    }
    requestedVenue.value = null;
    showToast("Venue requested. It is held while venue staff decide.");
    router.push({ name: "coordinator-event", params: { id: bookingEvent.value.id } });
  } catch {
    // Kept open so the coordinator sees why, beside the venue they picked.
  }
}
</script>

<template>
  <main class="py-8">
    <BauhausCard v-if="route.query.event" background="blue" accent="none" class="mb-10 text-canvas" data-testid="booking-event-context">
      <p v-if="eventError" role="alert" class="text-sm font-bold">{{ eventError }}</p>
      <template v-else-if="bookingEvent">
        <p class="text-xs font-bold opacity-80">Requesting a venue for</p>
        <p class="mt-1 text-2xl font-bold">{{ bookingEvent.name }}</p>
        <p v-if="bookingSpace" class="mt-1 text-sm font-bold">Space: {{ bookingSpace.label }}</p>
        <p class="mt-1 text-sm font-medium">{{ eventPeriod }}</p>
        <p v-if="!canRequest" class="mt-3 text-sm font-bold">
          {{ venuePanelState(bookingEvent, bookingSpace).reason ?? "This space already has a venue." }}
        </p>
        <p v-else-if="!searchMatchesEvent" class="mt-3 text-sm font-bold">
          Search the {{ bookingSpace ? "selected space's" : "event's own" }} date and times to request a venue for it.
        </p>
        <RouterLink
          :to="{ name: 'coordinator-event', params: { id: bookingEvent.id } }"
          class="mt-4 inline-block text-xs font-bold underline decoration-2 underline-offset-4"
        >
          Back to the event
        </RouterLink>
      </template>
      <p v-else class="text-sm font-bold">Loading event…</p>
    </BauhausCard>

    <SectionHeading id="find-a-venue" as="h1" tone="red" class="mb-6">Find a venue</SectionHeading>

    <section class="mb-10 border-4 border-ink bg-muted p-5 shadow-hard" data-testid="venue-filters" aria-labelledby="find-a-venue">
      <VenueCriteriaForm
        :criteria="venuesStore.criteria"
        :errors="venuesStore.fieldErrors"
        :is-loading="venuesStore.isLoading"
        @submit="venuesStore.search()"
        @reset="handleReset"
      />
    </section>

    <p
      v-if="venuesStore.error"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ venuesStore.error }}
    </p>

    <section v-if="venuesStore.hasSearched" aria-live="polite">
      <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <SectionHeading id="matching-venues" tone="blue">
            {{ venuesStore.includedCount }} matching {{ venuesStore.includedCount === 1 ? "venue" : "venues" }}
          </SectionHeading>
          <p v-if="!venuesStore.hasPeriod" class="mt-3 text-xs font-bold text-ink/70">
            Add a date and time to check availability
          </p>
          <p v-if="venuesStore.excludedCount > 0" class="mt-3 text-xs font-bold text-ink/70">
            Greyed-out venues don't meet every requirement. Each one lists what it is missing.
          </p>
        </div>
        <BauhausSelect
          v-if="venuesStore.includedCount > 1"
          v-model="sortKey"
          class="w-full sm:w-64"
          label="Sort by"
          aria-label="Sort venues by"
          :options="VENUE_SORT_OPTIONS"
          :show-placeholder="false"
          compact
        />
      </div>

      <p v-if="venuesStore.includedCount === 0" class="mb-8 text-sm font-medium">
        No venue meets every requirement. The greyed-out venues below show what each one is missing.
      </p>

      <div class="flex flex-col gap-6">
        <VenueResultCard v-for="result in orderedResults" :key="result.venue.id" :result="result">
          <template v-if="!result.excluded && canRequest && searchMatchesEvent && result.availability === 'available'" #actions>
            <BauhausButton variant="primary" :aria-label="`Request ${result.venue.name}`" @click="openRequest(result.venue)">
              Request this venue
            </BauhausButton>
          </template>
        </VenueResultCard>
      </div>
    </section>

    <RequestVenueModal
      v-if="bookingEvent && requestedVenue"
      :open="Boolean(requestedVenue)"
      :venue-name="requestedVenue.name"
      :event-name="bookingEvent.name"
      :period="eventPeriod"
      :busy="bookingStore.isRequesting"
      :error="bookingStore.error"
      :conflict="describeConflict(bookingStore.conflict, bookingEvent.event_timezone || 'Asia/Singapore')"
      :replaces-venue-name="replacedBooking?.venue_name ?? ''"
      :returns-to-planning="returnsToPlanning"
      :suitability="requestedSuitability"
      @confirm="confirmRequest"
      @cancel="requestedVenue = null"
    />
  </main>
</template>
