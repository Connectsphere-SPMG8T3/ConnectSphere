<script setup>
import { RouterLink } from "vue-router";

import { formatPublicEventDate, publicEventAvailabilityLabel } from "@/features/registrations/publicEvents";

defineProps({
  event: { type: Object, required: true },
  showStatus: { type: Boolean, default: false },
});
</script>

<template>
  <article class="flex min-w-0 flex-col border-4 border-ink bg-canvas shadow-hard">
    <div class="flex items-start justify-between gap-4 border-b-2 border-ink p-5">
      <div class="min-w-0">
        <p v-if="showStatus" class="text-xs font-bold">{{ event.status }}</p>
        <h3 :class="showStatus ? 'mt-2' : ''" class="break-words text-2xl font-bold leading-tight">
          {{ event.name }}
        </h3>
      </div>
      <span class="shrink-0 border-2 border-ink bg-bauhaus-blue px-3 py-2 text-center text-xs font-bold leading-tight text-canvas">
        {{ publicEventAvailabilityLabel(event.availability) }}
      </span>
    </div>
    <div class="flex flex-1 flex-col gap-4 p-5">
      <p class="text-sm font-bold">{{ formatPublicEventDate(event) }}</p>
      <p v-if="event.description" class="line-clamp-3 text-sm leading-relaxed text-ink/80">
        {{ event.description }}
      </p>
      <p class="mt-auto text-xs font-bold">
        {{ event.venues.map((venue) => venue.name).join(" · ") || "Venue details to be announced" }}
      </p>
      <RouterLink
        :to="{ name: 'public-event-detail', params: { id: event.id } }"
        class="mt-1 inline-flex items-center justify-center border-2 border-ink bg-bauhaus-blue px-6 py-3 text-sm font-bold text-canvas shadow-hard transition-transform active-press sm:border-4"
      >View event</RouterLink>
    </div>
  </article>
</template>
