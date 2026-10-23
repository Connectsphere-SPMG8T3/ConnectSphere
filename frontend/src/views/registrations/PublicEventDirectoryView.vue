<script setup>
import { onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BrandMark from "@/components/common/BrandMark.vue";
import { useRegistrationStore } from "@/features/registrations/store";

const store = useRegistrationStore();

function eventDate(event) {
  if (!event.starts_at) return "Date to be announced";
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: event.event_timezone,
  }).format(new Date(event.starts_at));
}

function availabilityLabel(availability) {
  return {
    open: "Registration open",
    not_open: "Registration not open",
    closed: "Registration closed",
    full: "Full",
  }[availability] ?? "Registration unavailable";
}

onMounted(() => store.loadDirectory().catch(() => {}));
</script>

<template>
  <main class="min-h-screen bg-canvas py-8 text-ink">
    <header class="flex min-h-20 items-center justify-between border-b-4 border-ink px-5 py-4 sm:px-10">
      <RouterLink to="/" class="flex items-center gap-3" aria-label="ConnectSphere events">
        <BrandMark />
        <span class="text-lg font-bold leading-tight">ConnectSphere</span>
      </RouterLink>
      <RouterLink to="/login" class="text-sm font-bold underline decoration-2 underline-offset-4">Sign in</RouterLink>
    </header>

    <section class="border-b-4 border-ink bg-bauhaus-yellow px-5 py-10 sm:px-10 sm:py-14">
      <div class="mx-auto max-w-6xl">
        <p class="text-xs font-bold">Singapore events</p>
        <h1 class="mt-3 max-w-4xl text-4xl font-bold leading-tight sm:text-6xl">Find your next gathering</h1>
        <p class="mt-5 max-w-2xl text-base font-medium sm:text-lg">Browse confirmed events and see registration availability before you decide.</p>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-5 py-10 sm:px-10 sm:py-14" aria-labelledby="events-heading">
      <div class="mb-7 flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-4">
        <h2 id="events-heading" class="text-2xl font-bold">Upcoming events</h2>
        <p v-if="!store.isLoading && !store.error" class="text-xs font-bold">
          {{ store.events.length }} {{ store.events.length === 1 ? "event" : "events" }}
        </p>
      </div>
      <p v-if="store.isLoading" role="status" class="py-8 text-sm font-bold">Loading events…</p>
      <p v-else-if="store.error" role="alert" class="border-2 border-ink bg-bauhaus-red px-5 py-4 font-bold text-canvas">{{ store.error }}</p>
      <BauhausEmptyState v-else-if="!store.events.length" title="No public events yet" detail="Confirmed events will appear here when they are ready to share." />
      <div v-else class="grid grid-cols-1 gap-6 md:grid-cols-2">
        <article v-for="event in store.events" :key="event.id" class="flex min-w-0 flex-col border-4 border-ink bg-canvas shadow-hard">
          <div class="flex items-start justify-between gap-4 border-b-2 border-ink p-5">
            <div class="min-w-0">
              <p class="text-xs font-bold">{{ event.status }}</p>
              <h3 class="mt-2 break-words text-2xl font-bold leading-tight">{{ event.name }}</h3>
            </div>
            <span class="shrink-0 border-2 border-ink bg-bauhaus-blue px-3 py-2 text-center text-xs font-bold leading-tight text-canvas">{{ availabilityLabel(event.availability) }}</span>
          </div>
          <div class="flex flex-1 flex-col gap-4 p-5">
            <p class="text-sm font-bold">{{ eventDate(event) }}</p>
            <p v-if="event.description" class="line-clamp-3 text-sm leading-relaxed text-ink/80">{{ event.description }}</p>
            <p class="mt-auto text-xs font-bold">{{ event.venues.map((venue) => venue.name).join(" · ") || "Venue details to be announced" }}</p>
            <RouterLink
              :to="{ name: 'public-event-detail', params: { id: event.id } }"
              class="mt-1 inline-flex items-center justify-center border-2 border-ink bg-bauhaus-blue px-6 py-3 text-sm font-bold text-canvas shadow-hard transition-transform active-press sm:border-4"
            >View event</RouterLink>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>