<script setup>
import { RouterLink } from "vue-router";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import PublicFooter from "@/components/common/PublicFooter.vue";
import PublicHeader from "@/components/common/PublicHeader.vue";
import { formatEventDateRange } from "@/features/registrations/eventDateRange";

defineProps({
  event: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: "" },
  emptyTitle: { type: String, default: "Event unavailable" },
  emptyDetail: { type: String, default: "This event could not be found." },
  showHeader: { type: Boolean, default: true },
  backTo: { type: [String, Object], required: true },
  backLabel: { type: String, required: true },
});
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink">
    <PublicHeader v-if="showHeader">
      <RouterLink :to="backTo" class="text-sm font-bold underline decoration-2 underline-offset-4">
        {{ backLabel }}
      </RouterLink>
    </PublicHeader>

    <main class="py-8" data-testid="event-details-page">
      <div class="mx-auto max-w-5xl px-5 py-8 sm:px-10 sm:py-12">
        <p v-if="loading" role="status" class="py-8 text-sm font-bold">Loading event…</p>
        <p v-else-if="error" role="alert" class="border-2 border-ink bg-bauhaus-red px-5 py-4 font-bold text-canvas">
          {{ error }}
        </p>
        <BauhausEmptyState v-else-if="!event" :title="emptyTitle" :detail="emptyDetail" />

        <template v-else>
          <section class="border-4 border-ink bg-bauhaus-yellow p-6 shadow-hard sm:p-10">
            <h1 class="mt-3 break-words text-4xl font-bold leading-tight sm:text-6xl">{{ event.name }}</h1>
            <p class="mt-6 text-base font-bold sm:text-lg">
              {{ formatEventDateRange(event) }}
            </p>
          </section>

          <div class="mt-8 grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,1fr)_18rem]">
            <section class="min-w-0">
              <h2 class="border-b-2 border-ink pb-3 text-lg font-bold">About this event</h2>
              <p class="mt-4 whitespace-pre-line text-base leading-relaxed">
                {{ event.description || "Details will be announced soon." }}
              </p>
              <div class="mt-8">
                <h2 class="border-b-2 border-ink pb-3 text-lg font-bold">Venue</h2>
                <ul v-if="event.venues.length" class="divide-y-2 divide-ink/20">
                  <li v-for="venue in event.venues" :key="venue.id" class="py-4">
                    <p class="font-bold">{{ venue.name }}</p>
                    <p class="mt-1 text-sm">{{ venue.location }}</p>
                  </li>
                </ul>
                <p v-else class="py-4 text-sm font-medium">Venue details will be announced soon.</p>
              </div>
            </section>

            <aside class="h-fit border-4 border-ink bg-canvas p-5 shadow-hard">
              <slot name="sidebar" />
            </aside>
          </div>
        </template>
      </div>
    </main>
    <PublicFooter v-if="showHeader" />
  </div>
</template>
