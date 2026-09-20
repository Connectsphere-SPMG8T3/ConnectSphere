<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenuePhotoCarousel from "@/components/venues/VenuePhotoCarousel.vue";
import { blockReasonLabel, formatEventReference } from "@/features/venues/dashboard";
import {
  formatTurnaround,
  groupUpcomingBookings,
  lastEditorName,
  stepIndex,
  venueProfileTabs,
} from "@/features/venues/venueProfile";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS, useVenuesStore } from "@/features/venues/venueSearchStore";

const route = useRoute();
const venuesStore = useVenuesStore();

const labelFor = (list) => Object.fromEntries(list.map((entry) => [entry.value, entry.label]));
const layoutLabels = labelFor(LAYOUTS);
const facilityLabels = labelFor(FACILITIES);
const accessibilityLabels = labelFor(ACCESSIBILITY_FEATURES);

const venue = computed(() => venuesStore.selectedVenue);

const sgtFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatPeriod(period) {
  return `${sgtFormatter.format(new Date(period.starts_at))} – ${sgtFormatter.format(new Date(period.ends_at))}`;
}

const formatInstant = (value) => (value ? sgtFormatter.format(new Date(value)) : "Not recorded");

// SCRUM-67 AC2. `updated_at` comes from the SCRUM-39 trigger and is always
// present; `updated_by` is null until a venue is edited through a path that
// records the editor, so the two are worded separately rather than as one
// sentence that would read oddly with half of it missing.
const lastUpdated = computed(() => ({
  at: formatInstant(venue.value?.updated_at),
  by: lastEditorName(venue.value?.updated_by),
}));

// SCRUM-67 AC3. Counting and grouping live in features/venues/venueProfile.js,
// so the rules are testable without mounting this view.
const bookingGroups = computed(() => groupUpcomingBookings(venue.value?.upcoming_bookings));
const upcomingBookingCount = computed(() => venue.value?.upcoming_bookings?.length ?? 0);

// The tabs carry counts, so a closed tab never implies there is nothing in it.
const tabs = computed(() => venueProfileTabs(venue.value));
const activeTab = ref("capacity");
// A different venue should open on its first tab rather than keeping whichever
// one the previous venue was left on.
watch(() => route.params.id, () => { activeTab.value = "capacity"; });

function moveTab(delta) {
  const keys = tabs.value.map((tab) => tab.key);
  const next = stepIndex(keys.indexOf(activeTab.value), keys.length, delta);
  activeTab.value = keys[next];
}

// Tone → pill class maps are spelled out because Tailwind's scanner cannot see
// a class built by interpolation. VenueStaffDashboard keeps its own copy; see
// docs/IMPLEMENTATION_MAP.md §5 for the note on extracting it.
const pillClasses = {
  blue: "border-2 border-ink bg-bauhaus-blue text-canvas",
  yellow: "border-2 border-ink bg-bauhaus-yellow text-ink",
  red: "border-2 border-ink bg-bauhaus-red text-canvas",
  plain: "border-2 border-ink bg-canvas text-ink",
};

async function load() {
  try {
    await venuesStore.fetchVenue(route.params.id);
  } catch {
    // The store keeps the message; the template shows it.
  }
}

onMounted(load);
watch(() => route.params.id, load);
</script>

<template>
  <main class="py-12">
    <RouterLink
      :to="{ name: 'venue-search' }"
      class="mb-8 inline-block text-xs font-bold uppercase tracking-widest underline decoration-2 underline-offset-4"
    >
      ← Back to venue search
    </RouterLink>

    <p
      v-if="venuesStore.error && !venue"
      role="alert"
      class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ venuesStore.error }}
    </p>
    <p v-else-if="venuesStore.isLoading && !venue" class="text-sm font-medium">Loading venue…</p>

    <template v-if="venue">
      <VenuePhotoCarousel :photos="venue.photos ?? []" :venue-name="venue.name" data-testid="venue-photos" />

      <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow" class="mb-8">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">
          {{ venue.is_active ? "Venue" : "Inactive venue" }}
        </p>
        <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ venue.name }}</h1>
        <p class="mt-3 text-sm font-medium">{{ venue.location }}</p>
        <p v-if="venue.description" class="mt-3 max-w-xl text-sm font-medium opacity-90">{{ venue.description }}</p>
        <p class="mt-4 text-xs font-bold uppercase tracking-widest text-ink/70">
          Last updated {{ lastUpdated.at }} · by {{ lastUpdated.by }}
        </p>
      </BauhausCard>

      <div
        class="mb-6 flex flex-wrap gap-2"
        role="tablist"
        aria-label="Venue profile sections"
        @keydown.left.prevent="moveTab(-1)"
        @keydown.right.prevent="moveTab(1)"
      >
        <button
          v-for="tab in tabs"
          :id="`tab-${tab.key}`"
          :key="tab.key"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.key ? 'true' : 'false'"
          :aria-controls="`panel-${tab.key}`"
          :tabindex="activeTab === tab.key ? 0 : -1"
          class="border-2 border-ink px-4 py-2 text-xs font-bold uppercase tracking-widest active-press"
          :class="activeTab === tab.key ? 'bg-ink text-canvas shadow-hard' : 'bg-canvas text-ink'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}<span v-if="tab.count !== null"> · {{ tab.count }}</span>
        </button>
      </div>

      <BauhausCard
        v-if="activeTab === 'capacity'"
        id="panel-capacity"
        role="tabpanel"
        aria-labelledby="tab-capacity"
        background="white"
        accent="none"
      >
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Capacity &amp; hours</h2>
        <dl class="grid grid-cols-2 gap-y-2 text-sm">
          <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Capacity</dt>
          <dd class="font-medium">{{ venue.capacity }} pax</dd>
          <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Open</dt>
          <dd class="font-medium">{{ venue.opens_at.slice(0, 5) }}–{{ venue.closes_at.slice(0, 5) }}</dd>
          <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Turnaround</dt>
          <dd class="font-medium">{{ formatTurnaround(venue.turnaround_minutes) }}</dd>
        </dl>
        <h3 class="mb-2 mt-6 text-xs font-bold uppercase tracking-widest text-ink/70">Layouts</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="entry in venue.layouts"
            :key="entry.layout"
            class="border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-xs font-bold uppercase tracking-wide"
          >
            {{ layoutLabels[entry.layout] ?? entry.layout }}
            <span v-if="entry.capacity_for_layout">· {{ entry.capacity_for_layout }} pax</span>
          </li>
          <li v-if="!venue.layouts.length" class="text-sm font-medium">None recorded</li>
        </ul>
      </BauhausCard>

      <BauhausCard
        v-else-if="activeTab === 'facilities'"
        id="panel-facilities"
        role="tabpanel"
        aria-labelledby="tab-facilities"
        background="white"
        accent="none"
      >
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Facilities &amp; access</h2>
        <h3 class="mb-2 text-xs font-bold uppercase tracking-widest text-ink/70">Facilities</h3>
        <ul class="mb-6 flex flex-wrap gap-2">
          <li v-for="f in venue.facilities" :key="f" class="border-2 border-ink px-3 py-1 text-xs font-bold uppercase tracking-wide">
            {{ facilityLabels[f] ?? f }}
          </li>
          <li v-if="!venue.facilities.length" class="text-sm font-medium">None recorded</li>
        </ul>
        <h3 class="mb-2 text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="a in venue.accessibility_features"
            :key="a"
            class="border-2 border-ink px-3 py-1 text-xs font-bold uppercase tracking-wide"
          >
            {{ accessibilityLabels[a] ?? a }}
          </li>
          <li v-if="!venue.accessibility_features.length" class="text-sm font-medium">None recorded</li>
        </ul>
      </BauhausCard>

      <BauhausCard
        v-else-if="activeTab === 'bookings'"
        id="panel-bookings"
        role="tabpanel"
        aria-labelledby="tab-bookings"
        background="white"
        accent="none"
        data-testid="upcoming-bookings"
      >
        <div class="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-lg font-black uppercase tracking-tight">Upcoming bookings</h2>
          <p class="text-xs font-bold uppercase tracking-widest text-ink/70">
            {{ upcomingBookingCount }} upcoming {{ upcomingBookingCount === 1 ? "booking" : "bookings" }}
          </p>
        </div>
        <p class="mb-4 text-xs font-medium text-ink/70">
          Singapore time. Every booking here occupies the venue, tentative ones included.
        </p>

        <BauhausEmptyState
          v-if="upcomingBookingCount === 0"
          title="No upcoming bookings"
          detail="Nothing is confirmed or held on this venue from now on."
        />

        <div v-else class="flex flex-col gap-6">
          <section v-for="group in bookingGroups" :key="group.key">
            <div class="mb-2 flex flex-wrap items-center gap-3">
              <span :class="pillClasses[group.tone]" class="px-2 py-0.5 text-xs font-bold uppercase tracking-wide">
                {{ group.label }} · {{ group.bookings.length }}
              </span>
              <span class="text-xs font-medium text-ink/70">{{ group.detail }}</span>
            </div>
            <ul v-if="group.bookings.length" class="flex flex-col gap-2 text-sm">
              <li
                v-for="booking in group.bookings"
                :key="booking.id"
                class="flex flex-wrap items-center gap-x-3 gap-y-1 border-2 border-ink px-3 py-2"
              >
                <span class="font-bold uppercase tracking-wide">{{ formatEventReference(booking) }}</span>
                <span class="font-medium">{{ formatPeriod(booking.period) }}</span>
              </li>
            </ul>
            <p v-else class="text-sm font-medium text-ink/60">None.</p>
          </section>
        </div>
      </BauhausCard>

      <BauhausCard
        v-else
        id="panel-blocks"
        role="tabpanel"
        aria-labelledby="tab-blocks"
        background="white"
        accent="none"
        data-testid="upcoming-blocks"
      >
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Blocks</h2>
        <p class="mb-4 text-xs font-medium text-ink/70">
          Singapore time. Periods venue staff have made unbookable, from now on.
        </p>
        <ul class="flex flex-col gap-2 text-sm">
          <li v-for="block in venue.upcoming_blocks" :key="block.id" class="flex flex-wrap items-center gap-3">
            <span class="border-2 border-ink bg-bauhaus-red px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-canvas">
              {{ blockReasonLabel(block.reason) }}
            </span>
            <span class="font-medium">{{ formatPeriod(block.period) }}</span>
            <span v-if="block.notes" class="text-ink/70">{{ block.notes }}</span>
          </li>
          <li v-if="!venue.upcoming_blocks.length" class="font-medium">No blocks scheduled.</li>
        </ul>
      </BauhausCard>
    </template>
  </main>
</template>
