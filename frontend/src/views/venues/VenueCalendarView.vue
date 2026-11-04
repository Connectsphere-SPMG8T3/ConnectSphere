<script setup>
/**
 * A venue's availability calendar (SCRUM-57), for Venue Staff only (AC11; the
 * API enforces it). The venue is in the URL, so switching venue is a link
 * that can be shared or bookmarked. With no venue named, it opens the first
 * active one.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenueAvailabilityCalendar from "@/components/venues/VenueAvailabilityCalendar.vue";
import { useVenueCalendarStore } from "@/features/venues/venueCalendarStore";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const breadcrumbItems = computed(() => {
  const venue = store.calendar?.venue;
  return venue
    ? [
        { label: "Venues", to: { name: "venue-search" } },
        { label: venue.name, to: { name: "venue-detail", params: { id: venue.id } } },
        { label: "Calendar" },
      ]
    : [{ label: "Venues", to: { name: "venue-search" } }, { label: "Calendar" }];
});
const router = useRouter();
const auth = useAuthStore();
const store = useVenueCalendarStore();

const noVenues = ref(false);
const lookupError = ref("");

// Ticks each minute, so a hold that expires while the page is open stops
// showing as occupying the venue (AC6).
const now = ref(new Date());
let clock = null;

async function openFirstVenue() {
  try {
    const { results = [] } = await auth.withSession((token) => venuesApi.search({}, token));
    const first = results.find((result) => !result.excluded) ?? results[0];
    if (!first) {
      noVenues.value = true;
      return;
    }
    await router.replace({ name: "venue-calendar", params: { venueId: first.venue.id } });
  } catch (error) {
    lookupError.value = error.message;
  }
}

watch(
  () => route.params.venueId,
  (venueId) => {
    if (venueId) store.open(String(venueId));
    else openFirstVenue();
  },
  { immediate: true },
);

// Coming back to the tab (after approving a booking or adding a block
// elsewhere, say) asks again, without a page reload (AC4).
function refreshWhenVisible() {
  if (document.visibilityState === "visible") {
    now.value = new Date();
    store.refresh();
  }
}

onMounted(() => {
  clock = setInterval(() => {
    now.value = new Date();
  }, 60_000);
  document.addEventListener("visibilitychange", refreshWhenVisible);
});

onBeforeUnmount(() => {
  clearInterval(clock);
  document.removeEventListener("visibilitychange", refreshWhenVisible);
});

function selectVenue(venueId) {
  if (venueId && venueId !== store.venueId) router.push({ name: "venue-calendar", params: { venueId } });
}

function openDay(dayKey) {
  store.anchorKey = dayKey;
  store.view = "day";
  store.load();
}

function refresh() {
  now.value = new Date();
  store.refresh();
}
</script>

<template>
  <main class="py-8">
    <BauhausBreadcrumb :items="breadcrumbItems" />

    <h1 class="sr-only">{{ store.calendar?.venue?.name ?? "Venue calendar" }}</h1>

    <BauhausEmptyState
      v-if="noVenues"
      title="No venues yet"
      detail="Once a venue is added to the catalogue, its calendar shows here."
    />
    <p
      v-else-if="lookupError"
      class="border-2 border-bauhaus-red px-3 py-2 text-sm font-bold text-bauhaus-red"
      role="alert"
    >
      {{ lookupError }}
    </p>
    <VenueAvailabilityCalendar
      v-else-if="store.anchorKey"
      :calendar="store.calendar"
      :view="store.view"
      :anchor-key="store.anchorKey"
      :is-loading="store.isLoading"
      :has-loaded="store.hasLoaded"
      :error="store.error ?? ''"
      :now="now"
      @select-venue="selectVenue"
      @set-view="store.setView"
      @step="store.step"
      @today="store.goToToday()"
      @refresh="refresh"
      @open-day="openDay"
    />
  </main>
</template>
