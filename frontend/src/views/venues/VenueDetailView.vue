<script setup>
import { computed, onMounted, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS, useVenuesStore } from "@/stores/venues";

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

const humanise = (value) => value.replace(/_/g, " ");

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
      <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow" class="mb-8">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">
          {{ venue.is_active ? "Venue" : "Inactive venue" }}
        </p>
        <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ venue.name }}</h1>
        <p class="mt-3 text-sm font-medium">{{ venue.location }}</p>
        <p v-if="venue.description" class="mt-3 max-w-xl text-sm font-medium opacity-90">{{ venue.description }}</p>
      </BauhausCard>

      <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <BauhausCard background="white" accent="none">
          <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Capacity &amp; hours</h2>
          <dl class="grid grid-cols-2 gap-y-2 text-sm">
            <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Capacity</dt>
            <dd class="font-medium">{{ venue.capacity }} pax</dd>
            <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Open</dt>
            <dd class="font-medium">{{ venue.opens_at.slice(0, 5) }}–{{ venue.closes_at.slice(0, 5) }}</dd>
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

        <BauhausCard background="white" accent="none">
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

        <BauhausCard background="white" accent="none" class="sm:col-span-2">
          <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Upcoming unavailability</h2>
          <p class="mb-4 text-xs font-medium text-ink/70">Singapore time. Blocks and occupying bookings from now on.</p>
          <ul class="flex flex-col gap-2 text-sm">
            <li v-for="block in venue.upcoming_blocks" :key="block.id" class="flex flex-wrap items-center gap-3">
              <span class="border-2 border-ink bg-bauhaus-red px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-canvas">
                Blocked · {{ humanise(block.reason) }}
              </span>
              <span class="font-medium">{{ formatPeriod(block.period) }}</span>
              <span v-if="block.notes" class="text-ink/70">{{ block.notes }}</span>
            </li>
            <li v-for="booking in venue.upcoming_bookings" :key="booking.id" class="flex flex-wrap items-center gap-3">
              <span
                class="border-2 border-ink px-2 py-0.5 text-xs font-bold uppercase tracking-wide"
                :class="booking.status === 'held' ? 'bg-bauhaus-yellow text-ink' : 'bg-bauhaus-blue text-canvas'"
              >
                {{ booking.status === "held" ? "Tentative hold" : humanise(booking.status) }}
              </span>
              <span class="font-medium">{{ formatPeriod(booking.period) }}</span>
            </li>
            <li v-if="!venue.upcoming_blocks.length && !venue.upcoming_bookings.length" class="font-medium">
              Nothing scheduled.
            </li>
          </ul>
        </BauhausCard>
      </div>
    </template>
  </main>
</template>
