<script setup>
import { computed, nextTick, onMounted } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import EventPlanIllustration from "@/components/common/EventPlanIllustration.vue";
import PublicFooter from "@/components/common/PublicFooter.vue";
import PublicHeader from "@/components/common/PublicHeader.vue";
import TicketIllustration from "@/components/common/TicketIllustration.vue";
import { useRegistrationStore } from "@/features/registrations/store";

const store = useRegistrationStore();
const route = useRoute();
const router = useRouter();

// The landing page serves both audiences. The choice lives in the URL
// (?for=organisers) so a link can open the organiser view directly.
const audiences = [
  { key: "join", label: "Finding something fun to join" },
  { key: "organise", label: "Planning an event of my own" },
];
const intro = {
  join: "From talks to get-togethers, see what's on around Singapore and grab a spot before it fills up.",
  organise: "Bring your idea. We'll help sort the venue, the gear and the safety check, and keep you posted all the way.",
};

const audience = computed(() => (route.query.for === "organisers" ? "organise" : "join"));
const signupRole = computed(() => (audience.value === "organise" ? "organiser" : "attendee"));

const organiserSteps = [
  {
    title: "Pitch your idea",
    detail: "Share the date, how many people you expect, the layout and what you'll need. Save a draft anytime and submit when you're happy.",
    marker: "rounded-full bg-bauhaus-red text-canvas",
  },
  {
    title: "Meet your coordinator",
    detail: "A coordinator looks it over and may ask for a tweak or two before planning kicks off.",
    marker: "bg-bauhaus-blue text-canvas",
  },
  {
    title: "We sort the venue and gear",
    detail: "Venue staff and technical support lock in the space and equipment, and you'll hear about every step.",
    marker: "rounded-full bg-bauhaus-yellow text-ink",
  },
  {
    title: "Pass the safety check, then go",
    detail: "Once the safety check passes, your event is confirmed and attendees can sign up during the window you set.",
    marker: "bg-ink text-canvas",
  },
];

function selectAudience(key) {
  const { for: _ignored, ...query } = route.query;
  return router.replace({ query: key === "organise" ? { ...query, for: "organisers" } : query });
}

// Tabs pattern: the arrow keys (and Home/End) move the selection and focus together.
async function onTabKeydown(keyEvent) {
  const index = audiences.findIndex((option) => option.key === audience.value);
  const next = {
    ArrowRight: (index + 1) % audiences.length,
    ArrowLeft: (index - 1 + audiences.length) % audiences.length,
    Home: 0,
    End: audiences.length - 1,
  }[keyEvent.key];
  if (next === undefined) return;
  keyEvent.preventDefault();
  await selectAudience(audiences[next].key);
  await nextTick();
  document.getElementById(`audience-tab-${audiences[next].key}`)?.focus();
}

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
  <div class="min-h-screen bg-canvas text-ink">
    <PublicHeader>
      <BauhausButton to="/login" variant="outline" size="sm">Sign in</BauhausButton>
      <BauhausButton :to="{ name: 'signup', params: { role: signupRole } }" size="sm">Sign up</BauhausButton>
    </PublicHeader>

    <!-- pt-0 pb-0: the yellow hero runs edge to edge under the header, and each
         panel's own padding sets the space above the footer. -->
    <main class="py-8 pt-0 pb-0">
      <section class="overflow-hidden border-b-4 border-ink bg-bauhaus-yellow px-5 py-10 sm:px-10 sm:py-14">
        <div class="mx-auto flex max-w-6xl items-center justify-between gap-10">
          <div class="min-w-0">
            <p class="text-xs font-bold">Hey there, Singapore</p>
            <h1 class="mt-3 text-4xl font-bold leading-tight sm:text-6xl">What are you up to?</h1>
            <div role="tablist" aria-label="What are you up to?" class="mt-8 flex flex-col gap-4 sm:flex-row">
              <button
                v-for="option in audiences"
                :id="`audience-tab-${option.key}`"
                :key="option.key"
                type="button"
                role="tab"
                aria-controls="audience-panel"
                :aria-selected="audience === option.key ? 'true' : 'false'"
                :tabindex="audience === option.key ? 0 : -1"
                class="inline-flex items-center gap-3 border-4 border-ink px-5 py-4 text-left text-base font-bold shadow-hard transition-transform active-press sm:text-lg"
                :class="audience === option.key ? 'bg-ink text-canvas' : 'bg-canvas text-ink hover:bg-muted'"
                @click="selectAudience(option.key)"
                @keydown="onTabKeydown"
              >
                {{ option.label }}
              </button>
            </div>
            <p class="mt-6 max-w-2xl text-base font-medium sm:text-lg">{{ intro[audience] }}</p>
          </div>
          <!-- Decorative: a ticket for joining, a plan for organising. -->
          <div data-testid="hero-illustration" class="hidden h-64 w-72 shrink-0 items-center justify-center lg:flex" aria-hidden="true">
            <TicketIllustration v-if="audience === 'join'" animated />
            <EventPlanIllustration v-else animated />
          </div>
        </div>
      </section>

      <div id="audience-panel" role="tabpanel" :aria-labelledby="`audience-tab-${audience}`" tabindex="0">
        <section v-if="audience === 'join'" class="mx-auto max-w-6xl px-5 py-10 sm:px-10 sm:py-14" aria-labelledby="events-heading">
          <div class="mb-7 flex flex-wrap items-end justify-between gap-4 border-b-2 border-ink pb-4">
            <h2 id="events-heading" class="text-2xl font-bold">Happening soon</h2>
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

        <section v-else class="mx-auto max-w-6xl px-5 py-10 sm:px-10 sm:py-14" aria-labelledby="organise-heading">
          <div class="mb-7 border-b-2 border-ink pb-4">
            <h2 id="organise-heading" class="text-2xl font-bold">From idea to event in four steps</h2>
          </div>
          <ol class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <li v-for="(step, index) in organiserSteps" :key="step.title" class="flex flex-col border-4 border-ink bg-canvas p-5 shadow-hard">
              <span class="flex h-12 w-12 items-center justify-center border-2 border-ink text-lg font-bold" :class="step.marker" aria-hidden="true">{{ index + 1 }}</span>
              <h3 class="mt-4 text-lg font-bold leading-tight">{{ step.title }}</h3>
              <p class="mt-2 text-sm leading-relaxed">{{ step.detail }}</p>
            </li>
          </ol>
          <div class="mt-10 flex flex-col items-start gap-5 border-4 border-ink bg-bauhaus-blue p-6 text-canvas shadow-hard md:flex-row md:items-center md:justify-between">
            <p class="text-2xl font-bold leading-tight">Got an idea? Let's make it happen!</p>
            <BauhausButton :to="{ name: 'signup', params: { role: 'organiser' } }" variant="outline">Create organiser account</BauhausButton>
          </div>
        </section>
      </div>
    </main>

    <PublicFooter />
  </div>
</template>
