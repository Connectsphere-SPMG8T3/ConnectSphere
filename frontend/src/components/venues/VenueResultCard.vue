<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import SuitabilityBadge from "@/components/venues/SuitabilityBadge.vue";
import SuitabilityFindings from "@/components/venues/SuitabilityFindings.vue";
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

// "Right room, wrong time" and "wrong room" are kept visually distinct:
// availability is a badge of its own, suitability reasons are a list.
const availabilityBadge = computed(() => {
  switch (props.result.availability) {
    case "available":
      return { text: "Available", classes: "bg-bauhaus-blue text-canvas" };
    case "unavailable":
      return { text: "Unavailable", classes: "bg-bauhaus-red text-canvas" };
    default:
      return { text: "Availability not checked", classes: "bg-surface text-ink" };
  }
});

const layouts = computed(() =>
  venue.value.layouts.map((entry) =>
    entry.capacity_for_layout
      ? `${layoutLabels[entry.layout] ?? entry.layout} (${entry.capacity_for_layout})`
      : (layoutLabels[entry.layout] ?? entry.layout),
  ),
);
const facilities = computed(() => venue.value.facilities.map((f) => facilityLabels[f] ?? f));
const accessibility = computed(() => venue.value.accessibility_features.map((a) => accessibilityLabels[a] ?? a));

const hours = computed(() => `${venue.value.opens_at.slice(0, 5)}–${venue.value.closes_at.slice(0, 5)}`);
</script>

<template>
  <BauhausCard background="white" accent="none" class="h-full">
    <div class="flex h-full flex-col gap-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-2xl font-black uppercase leading-none tracking-tight">
            <RouterLink :to="{ name: 'venue-detail', params: { id: venue.id } }" class="underline decoration-2 underline-offset-4">
              {{ venue.name }}
            </RouterLink>
          </h3>
          <p class="mt-1 text-sm font-medium">{{ venue.location }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <SuitabilityBadge :suitability="result.suitability" />
          <span
            data-testid="availability-badge"
            class="border-2 border-ink px-3 py-1 text-xs font-bold uppercase tracking-widest"
            :class="availabilityBadge.classes"
          >
            {{ availabilityBadge.text }}
          </span>
        </div>
      </div>

      <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Capacity</dt>
        <dd class="font-medium">{{ venue.capacity }} pax</dd>
        <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Hours</dt>
        <dd class="font-medium">{{ hours }}</dd>
        <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Layouts</dt>
        <dd class="font-medium">{{ layouts.length ? layouts.join(", ") : "—" }}</dd>
        <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Facilities</dt>
        <dd class="font-medium">{{ facilities.length ? facilities.join(", ") : "—" }}</dd>
        <dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility</dt>
        <dd class="font-medium">{{ accessibility.length ? accessibility.join(", ") : "None recorded" }}</dd>
      </dl>

      <div v-if="result.suitability?.reasons?.length" class="mt-auto border-t-2 border-ink pt-3">
        <SuitabilityFindings :suitability="result.suitability" />
      </div>

      <ul v-if="result.reasons.length" class="mt-auto flex flex-col gap-1 border-t-2 border-ink pt-3">
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

      <!-- An action on this venue, e.g. "Request this venue" when the search was opened from an event (SCRUM-19). -->
      <div v-if="$slots.actions" class="mt-auto border-t-2 border-ink pt-4">
        <slot name="actions" />
      </div>
    </div>
  </BauhausCard>
</template>
