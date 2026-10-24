<script setup>
import { computed, onMounted } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import PublicFooter from "@/components/common/PublicFooter.vue";
import PublicHeader from "@/components/common/PublicHeader.vue";
import { showToast } from "@/composables/useToast";
import { useRegistrationStore } from "@/features/registrations/store";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useRegistrationStore();
const event = computed(() => store.event);

function eventDate(value, timeZone) {
  if (!value) return "To be announced";
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone,
  }).format(new Date(value));
}

const availabilityLabels = {
  open: "Registration open",
  not_open: "Registration not open yet",
  closed: "Registration closed",
  full: "Full",
};
const canRegister = computed(() => event.value?.availability === "open");
const hasRegistered = computed(() => ["registered", "already_registered"].includes(store.registrationResult?.status));
const mustChooseAttendeeRole = computed(() => auth.isAuthenticated && auth.role !== "attendee");

async function handleRegister() {
  if (!auth.isAuthenticated) {
    await router.push({ name: "login", query: { redirect: route.fullPath } });
    return;
  }
  if (mustChooseAttendeeRole.value) return;
  try {
    const result = await store.register(route.params.id);
    showToast(result.status === "already_registered"
      ? "You are already registered for this event."
      : "You are registered for this event.");
  } catch {
    return;
  }
}

onMounted(() => store.loadEvent(route.params.id).catch(() => {}));
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink">
    <PublicHeader>
      <RouterLink to="/" class="text-sm font-bold underline decoration-2 underline-offset-4">All events</RouterLink>
    </PublicHeader>

    <main class="py-8">
      <div class="mx-auto max-w-5xl px-5 sm:px-10">
        <p v-if="store.isLoading" role="status" class="py-8 text-sm font-bold">Loading event…</p>
        <p v-else-if="store.error && !event" role="alert" class="border-2 border-ink bg-bauhaus-red px-5 py-4 font-bold text-canvas">{{ store.error }}</p>
        <BauhausEmptyState v-else-if="!event" title="Event unavailable" detail="This event could not be found." />

        <template v-else>
          <section class="border-4 border-ink bg-bauhaus-yellow p-6 shadow-hard sm:p-10">
            <p class="text-xs font-bold">{{ event.status }}</p>
            <h1 class="mt-3 break-words text-4xl font-bold leading-tight sm:text-6xl">{{ event.name }}</h1>
            <p class="mt-6 text-base font-bold sm:text-lg">{{ eventDate(event.starts_at, event.event_timezone) }}</p>
            <p v-if="event.ends_at" class="mt-1 text-sm font-medium">Ends {{ eventDate(event.ends_at, event.event_timezone) }}</p>
          </section>

          <div class="mt-8 grid grid-cols-1 gap-8 md:grid-cols-[minmax(0,1fr)_18rem]">
            <section class="min-w-0">
              <h2 class="border-b-2 border-ink pb-3 text-lg font-bold">About this event</h2>
              <p class="mt-4 whitespace-pre-line text-base leading-relaxed">{{ event.description || "Details will be announced soon." }}</p>
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
              <h2 class="text-lg font-bold">{{ availabilityLabels[event.availability] || "Registration unavailable" }}</h2>
              <p v-if="event.effective_capacity" class="mt-3 text-sm font-medium">{{ event.registered_count }} of {{ event.effective_capacity }} places registered</p>
              <p v-if="store.error" role="alert" class="mt-4 border-2 border-ink bg-bauhaus-red p-3 text-sm font-bold text-canvas">{{ store.error }}</p>
              <p v-if="mustChooseAttendeeRole" class="mt-4 text-sm font-bold">Switch your active role to Attendee to register.</p>
              <BauhausButton v-if="hasRegistered" class="mt-5 w-full" variant="primary" disabled>
                Registered
              </BauhausButton>
              <BauhausButton v-else-if="canRegister" class="mt-5 w-full" variant="primary" :disabled="store.isRegistering || mustChooseAttendeeRole" @click="handleRegister">
                {{ store.isRegistering ? "Registering…" : "Register" }}
              </BauhausButton>
              <BauhausButton v-else-if="event.availability === 'full' && event.waitlist_enabled" class="mt-5 w-full" variant="secondary" disabled>
                Join waitlist
              </BauhausButton>
              <RouterLink
                v-else-if="event.availability === 'not_open' && !auth.isAuthenticated"
                :to="{ name: 'signup', params: { role: 'attendee' }, query: { redirect: route.fullPath } }"
                class="mt-5 block text-sm font-bold underline decoration-2 underline-offset-4"
              >Create an Attendee account</RouterLink>
            </aside>
          </div>
        </template>
      </div>
    </main>

    <PublicFooter />
  </div>
</template>