<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import VenueGallery from "@/components/venues/VenueGallery.vue";
import SuitabilityBadge from "@/components/venues/SuitabilityBadge.vue";
import SuitabilityFindings from "@/components/venues/SuitabilityFindings.vue";
import { venueSlides } from "@/features/venues/venueProfile";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

const props = defineProps({
  result: {
    type: Object,
    required: true,
  },
});

const labelFor = (list) => Object.fromEntries(list.map((entry) => [entry.value, entry.label]));
const layoutLabels = labelFor(LAYOUTS);
const facilityLabels = labelFor(FACILITIES);
const accessibilityLabels = labelFor(ACCESSIBILITY_FEATURES);

const venue = computed(() => props.result.venue);
const slides = computed(() => venueSlides(venue.value));

// "Right room, wrong time" and "wrong room" are kept visually distinct:
// availability is a badge of its own, suitability reasons are a list. With no
// date and time in the search availability was not checked, so no badge says so.
const availabilityBadge = computed(() => {
  switch (props.result.availability) {
    case "available":
      return { text: "Available", classes: "bg-bauhaus-blue text-canvas" };
    case "unavailable":
      return { text: "Unavailable", classes: "bg-bauhaus-red text-canvas" };
    default:
      return null;
  }
});

// Each layout chip previews its own slide in the carousel (`slideKey` matches `venueSlides`).
const layouts = computed(() =>
  venue.value.layouts.map((entry) => ({
    label: entry.capacity_for_layout
      ? `${layoutLabels[entry.layout] ?? entry.layout} (${entry.capacity_for_layout})`
      : (layoutLabels[entry.layout] ?? entry.layout),
    slideKey: `layout-${entry.layout}`,
  })),
);
const slideIndex = ref(0);
const activeSlideKey = computed(() => slides.value[slideIndex.value]?.key ?? null);

function previewLayout(slideKey) {
  const target = slides.value.findIndex((slide) => slide.key === slideKey);
  if (target >= 0) slideIndex.value = target;
}

const facilities = computed(() => venue.value.facilities.map((f) => ({ label: facilityLabels[f] ?? f })));
const accessibility = computed(() => venue.value.accessibility_features.map((a) => ({ label: accessibilityLabels[a] ?? a })));

const detailGroups = computed(() => [
  { label: "Layouts", hint: "Select one to preview it", items: layouts.value, empty: "—" },
  { label: "Facilities", items: facilities.value, empty: "—" },
  { label: "Accessibility", items: accessibility.value, empty: "None recorded" },
]);

// The time the venue is held before and after a booking (CR-100); a venue that records none shows 0.
const minutes = (value) => `${value ?? 0} min`;

const hours = computed(() => `${venue.value.opens_at.slice(0, 5)}–${venue.value.closes_at.slice(0, 5)}`);
</script>

<template>
  <BauhausCard background="white" accent="none" compact :dimmed="result.excluded" class="h-full" data-testid="venue-result">
    <!-- Each card is as tall as its content. One venue per row: the image carousel on the left, the venue's name and what it offers in the
         middle, and on the right the figures, the verdicts and the action (below on narrow screens). -->
    <div class="grid grid-cols-1 gap-5 md:grid-cols-[15rem_minmax(0,1fr)] lg:grid-cols-[15rem_minmax(0,1fr)_13rem]">
      <VenueGallery v-model:index="slideIndex" compact :slides="slides" :venue-name="venue.name" class="self-start" />

      <div class="flex min-w-0 flex-col gap-4">
        <div>
          <h3 class="text-2xl font-bold leading-tight">
            <RouterLink :to="{ name: 'venue-detail', params: { id: venue.id } }" class="underline decoration-2 underline-offset-4">
              {{ venue.name }}
            </RouterLink>
          </h3>
          <p class="mt-1 text-sm font-medium">{{ venue.location }}</p>
        </div>

        <dl class="flex flex-col gap-4 border-t-2 border-ink pt-4">
          <div v-for="group in detailGroups" :key="group.label" class="grid gap-2 sm:grid-cols-[7rem_minmax(0,1fr)] sm:gap-4">
            <dt>
              <span class="block text-sm font-bold">{{ group.label }}</span>
              <span v-if="group.hint && group.items.length > 1" class="block text-xs font-medium text-ink/70">{{ group.hint }}</span>
            </dt>
            <dd>
              <ul v-if="group.items.length" class="flex flex-wrap gap-2">
                <li v-for="item in group.items" :key="item.label">
                  <button
                    v-if="item.slideKey"
                    type="button"
                    :aria-pressed="activeSlideKey === item.slideKey"
                    :aria-label="`Preview the ${item.label} layout`"
                    class="border-2 border-ink px-3 py-1 text-sm font-bold active-press"
                    :class="activeSlideKey === item.slideKey ? 'bg-bauhaus-yellow' : 'bg-canvas hover:bg-muted'"
                    @click="previewLayout(item.slideKey)"
                  >
                    {{ item.label }}
                  </button>
                  <span v-else class="inline-block border-2 border-ink bg-canvas px-3 py-1 text-sm font-medium">{{ item.label }}</span>
                </li>
              </ul>
              <span v-else class="text-sm font-medium text-ink/70">{{ group.empty }}</span>
            </dd>
          </div>
        </dl>

        <div v-if="result.suitability?.reasons?.length" class="border-t-2 border-ink pt-3">
          <SuitabilityFindings :suitability="result.suitability" />
        </div>

        <ul v-if="result.reasons.length" class="flex flex-col gap-1 border-t-2 border-ink pt-3">
          <li
            v-for="reason in result.reasons"
            :key="reason.code + reason.message"
            class="flex items-start gap-2 text-sm font-bold"
            :class="['blocked', 'held', 'booked'].includes(reason.code) ? 'text-bauhaus-red' : 'text-ink'"
          >
            <span class="mt-1.5 inline-block h-2 w-2 shrink-0 bg-current" aria-hidden="true" />
            {{ reason.message }}
          </li>
        </ul>
      </div>

      <div
        class="flex flex-col gap-4 border-t-2 border-ink pt-4 md:col-span-2 lg:col-span-1 lg:border-l-2 lg:border-t-0 lg:pl-5 lg:pt-0"
      >
        <dl class="grid grid-cols-2 gap-4 lg:grid-cols-1">
          <div>
            <dt class="text-xs font-bold text-ink/70">Capacity</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ venue.capacity }} <span class="text-sm">pax</span></dd>
          </div>
          <div>
            <dt class="text-xs font-bold text-ink/70">Open</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ hours }}</dd>
          </div>
          <div>
            <dt class="text-xs font-bold text-ink/70">Setup</dt>
            <dd class="mt-1 text-base font-bold leading-tight">{{ minutes(venue.setup_minutes) }}</dd>
          </div>
          <div>
            <dt class="text-xs font-bold text-ink/70">Turnaround</dt>
            <dd class="mt-1 text-base font-bold leading-tight">{{ minutes(venue.turnaround_minutes) }}</dd>
          </div>
        </dl>

        <div class="flex flex-wrap gap-2">
          <SuitabilityBadge :suitability="result.suitability" />
          <span
            v-if="availabilityBadge"
            data-testid="availability-badge"
            class="border-2 border-ink px-3 py-1 text-xs font-bold"
            :class="availabilityBadge.classes"
          >
            {{ availabilityBadge.text }}
          </span>
        </div>

        <!-- An action on this venue, e.g. "Request this venue" when the search was opened from an event (SCRUM-19). -->
        <div v-if="$slots.actions" class="lg:mt-auto">
          <slot name="actions" />
        </div>
      </div>
    </div>
  </BauhausCard>
</template>
