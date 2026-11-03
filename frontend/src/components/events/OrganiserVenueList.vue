<script setup>
import { venueWindowLabel } from "@/features/events/organiserVenues";

// CR-111 AC2 to AC4: each venue on the organiser's event, separately. The API sends only
// what an organiser may see, so this component shows every field it is given.
defineProps({
  venues: { type: Array, default: () => [] },
  timezone: { type: String, default: "Asia/Singapore" },
});
</script>

<template>
  <section v-if="venues.length" data-testid="organiser-venues">
    <h3 class="text-xl font-bold">Venues</h3>
    <ul class="mt-3 grid gap-3">
      <li
        v-for="venue in venues"
        :key="venue.booking_id"
        data-testid="organiser-venue"
        :data-status="venue.status"
        class="border-2 border-ink p-3 font-medium"
        :class="venue.status === 'affected' ? 'bg-bauhaus-yellow' : 'bg-canvas'"
      >
        <div class="flex flex-wrap items-start justify-between gap-2">
          <p>
            <strong>{{ venue.venue_name }}</strong>
            <span v-if="venue.space_label"> · {{ venue.space_label }}</span>
          </p>
          <p class="flex flex-wrap gap-2 text-xs font-bold">
            <span v-if="venue.is_primary" class="border-2 border-ink bg-bauhaus-blue px-2 py-1 text-canvas">Primary venue</span>
            <span class="border-2 border-ink bg-canvas px-2 py-1 text-ink">{{ venue.status_label }}</span>
          </p>
        </div>
        <p v-if="venue.location" class="mt-1 text-sm">{{ venue.location }}</p>
        <p class="text-sm">{{ venueWindowLabel(venue.starts_at, venue.ends_at, timezone) }}</p>
        <p class="mt-2 text-sm font-bold">{{ venue.next_action }}</p>
      </li>
    </ul>
  </section>
</template>
