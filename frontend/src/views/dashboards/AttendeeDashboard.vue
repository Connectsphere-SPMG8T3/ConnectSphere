<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import PublicEventCard from "@/components/registrations/PublicEventCard.vue";
import calendarArrowDown from "@/assets/icons/calendar-arrow-down.svg";
import calendarArrowUp from "@/assets/icons/calendar-arrow-up.svg";
import { BOARD_CARD_CLASSES, BOARD_CARD_TONE_CLASSES } from "@/features/events/dashboard";
import { filterAndSortPublicEvents } from "@/features/registrations/publicEvents";
import {
  filterAndSortRegistrations,
  formatRegistrationPeriod,
  registrationStatusLabel,
  splitRegistrationsByEndTime,
  summarizeAttendeeDashboard,
} from "@/features/registrations/registeredEvents";
import { useRegistrationStore } from "@/features/registrations/store";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const registrationStore = useRegistrationStore();
const route = useRoute();
const activeTab = computed(() => ["events", "explore"].includes(route.query.tab) ? route.query.tab : "overview");
const registrationPeriod = ref("all");
const registrationSearch = ref("");
const registrationStatuses = ref([]);
const registrationSortField = ref("date");
const registrationSortDirection = ref("asc");
const eventSearch = ref("");
const eventSortField = ref("date");
const eventSortDirection = ref("asc");

const summary = computed(() =>
  summarizeAttendeeDashboard(registrationStore.myRegistrations, registrationStore.events),
);
const summaryCards = computed(() => [
  {
    key: "upcoming-registrations",
    label: "Upcoming registrations",
    value: registrationStore.isLoadingMyRegistrations || registrationStore.myRegistrationsError
      ? "—"
      : summary.value.upcomingRegistrations,
    detail: registrationStore.isLoadingMyRegistrations
      ? "Loading your registrations"
      : registrationStore.myRegistrationsError
        ? "Registration count unavailable"
        : "Registered or waitlisted events still in progress or upcoming",
    background: "blue",
    accent: "circle",
    accentColor: "bauhaus-yellow",
  },
  {
    key: "open-events",
    label: "Events open for registration",
    value: registrationStore.isLoading || registrationStore.error ? "—" : summary.value.openEvents,
    detail: registrationStore.isLoading
      ? "Loading public events"
      : registrationStore.error
        ? "Public event count unavailable"
        : "Public events accepting registrations",
    background: "white",
    accent: "square",
    accentColor: "bauhaus-red",
  },
  {
    key: "past-registrations",
    label: "Past registrations",
    value: registrationStore.isLoadingMyRegistrations || registrationStore.myRegistrationsError
      ? "—"
      : summary.value.pastRegistrations,
    detail: registrationStore.isLoadingMyRegistrations
      ? "Loading your registrations"
      : registrationStore.myRegistrationsError
        ? "Registration count unavailable"
        : "Registered events that have ended",
    background: "red",
    accent: "triangle",
    accentColor: "bauhaus-yellow",
  },
]);

const registrationSortOptions = [
  { value: "date", label: "Event date" },
  { value: "name", label: "Event name" },
];
const registrationSortLabels = Object.fromEntries(
  registrationSortOptions.map((option) => [option.value, option.label]),
);
const registrationDirectionLabel = computed(
  () => `${registrationSortDirection.value === "asc" ? "Ascending" : "Descending"} by ${registrationSortLabels[registrationSortField.value]}`,
);
const registrationDirectionIcon = computed(() =>
  registrationSortDirection.value === "asc" ? calendarArrowUp : calendarArrowDown,
);
const filteredRegistrations = computed(() =>
  filterAndSortRegistrations(registrationStore.myRegistrations, {
    search: registrationSearch.value,
    statuses: registrationStatuses.value,
    period: registrationPeriod.value,
    sortBy: registrationSortField.value,
    direction: registrationSortDirection.value,
  }),
);
const eventGroups = computed(() => {
  const groups = splitRegistrationsByEndTime(filteredRegistrations.value);
  return [
    { key: "upcoming", title: "Upcoming", registrations: groups.upcoming },
    { key: "past", title: "Past", registrations: groups.past },
  ].filter((group) => registrationPeriod.value === "all" || registrationPeriod.value === group.key);
});

const registrationStatusOptions = [
  { value: "registered", label: "Registered" },
  { value: "waitlisted", label: "Waitlisted" },
];
const publicEventSortOptions = [
  { value: "date", label: "Event date" },
  { value: "name", label: "Event name" },
];
const publicEventSortLabels = Object.fromEntries(
  publicEventSortOptions.map((option) => [option.value, option.label]),
);
const visiblePublicEvents = computed(() =>
  filterAndSortPublicEvents(registrationStore.events, {
    search: eventSearch.value,
    sortBy: eventSortField.value,
    direction: eventSortDirection.value,
  }),
);
const sortDirectionLabel = computed(
  () => `${eventSortDirection.value === "asc" ? "Ascending" : "Descending"} by ${publicEventSortLabels[eventSortField.value]}`,
);
const sortDirectionIcon = computed(() =>
  eventSortDirection.value === "asc" ? calendarArrowUp : calendarArrowDown,
);

function toggleSortDirection() {
  eventSortDirection.value = eventSortDirection.value === "asc" ? "desc" : "asc";
}

function toggleRegistrationSortDirection() {
  registrationSortDirection.value = registrationSortDirection.value === "asc" ? "desc" : "asc";
}

function clearRegistrationFilters() {
  registrationSearch.value = "";
  registrationStatuses.value = [];
  registrationPeriod.value = "all";
  registrationSortField.value = "date";
  registrationSortDirection.value = "asc";
}

function registrationCardTone(status) {
  return status === "registered" ? "done" : "waiting";
}

onMounted(() => {
  registrationStore.loadMyRegistrations().catch(() => {});
  registrationStore.loadDirectory().catch(() => {});
});
</script>

<template>
  <main class="py-8">
    <section v-if="activeTab === 'overview'" aria-labelledby="overview-heading">
      <BauhausCard background="blue" accent="none" class="mb-10">
        <p class="text-xs font-bold opacity-80">Attendee dashboard</p>
        <h1 id="overview-heading" class="mt-2 text-4xl font-bold leading-tight sm:text-5xl">
          Welcome, {{ authStore.profile?.full_name }}
        </h1>
        <p class="mt-3 max-w-xl text-sm font-medium">
          Browse confirmed public events, register your attendance, and keep track of the events
          you're going to.
        </p>
      </BauhausCard>

      <p v-if="registrationStore.myRegistrationsError" role="alert" class="mb-4 text-sm font-bold text-bauhaus-red">
        {{ registrationStore.myRegistrationsError }}
      </p>
      <p v-if="registrationStore.error" role="alert" class="mb-4 text-sm font-bold text-bauhaus-red">
        {{ registrationStore.error }}
      </p>
      <section aria-label="Attendee overview">
        <div class="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          <BauhausSummaryCard
            v-for="card in summaryCards"
            :key="card.key"
            :data-testid="`summary-${card.key}`"
            :label="card.label"
            :value="card.value"
            :detail="card.detail"
            :background="card.background"
            :accent="card.accent"
            :accent-color="card.accentColor"
          />
        </div>
      </section>
    </section>

    <section v-else-if="activeTab === 'events'" aria-labelledby="my-events-heading">
      <section
        data-testid="registration-filters"
        class="mb-8 border-4 border-ink bg-muted p-5 shadow-hard"
        aria-labelledby="my-events-heading"
      >
        <h1 id="my-events-heading" class="sr-only">My events</h1>
        <div class="mb-5 flex items-center justify-between gap-4">
          <h2 class="text-2xl font-bold">Find my event</h2>
          <BauhausButton
            class="shrink-0 px-4 py-2 text-xs shadow-none sm:border-2"
            variant="yellow"
            aria-label="Clear my event filters"
            @click="clearRegistrationFilters"
          >Clear</BauhausButton>
        </div>
        <div class="flex flex-col items-stretch gap-3">
          <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
            <BauhausInput
              v-model="registrationSearch"
              class="w-full sm:min-w-0 sm:flex-[1.4_1_0%]"
              label="Event name"
              placeholder="Search by event name"
              aria-label="Search my events"
              compact
            />
            <BauhausSelect
              v-model="registrationStatuses"
              class="w-full sm:min-w-0 sm:flex-1"
              label="Status"
              aria-label="Filter registrations by status"
              :options="registrationStatusOptions"
              multiple
              compact
            />
          </div>
          <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
            <div class="flex flex-wrap gap-2" role="group" aria-label="Filter my events by time">
              <BauhausButton
                v-for="period in [
                  { key: 'all', label: 'All' },
                  { key: 'upcoming', label: 'Upcoming' },
                  { key: 'past', label: 'Past' },
                ]"
                :key="period.key"
                variant="outline"
                class="shadow-none"
                :aria-pressed="registrationPeriod === period.key"
                :class="registrationPeriod === period.key ? '!bg-ink !text-canvas' : ''"
                @click="registrationPeriod = period.key"
              >{{ period.label }}</BauhausButton>
            </div>
            <div class="flex w-full items-end gap-3 sm:ml-auto sm:w-auto">
              <BauhausSelect
                v-model="registrationSortField"
                class="min-w-0 flex-1"
                label="Sort by"
                aria-label="Sort my events by"
                :options="registrationSortOptions"
                :show-placeholder="false"
                dropdown
                compact
              />
              <button
                type="button"
                class="h-[50px] w-12 shrink-0 border-2 border-ink bg-canvas px-3 text-lg font-bold leading-none text-ink shadow-none outline-none transition-colors hover:bg-muted focus:bg-muted"
                :aria-label="`Toggle sort direction, currently ${registrationDirectionLabel}`"
                :title="registrationDirectionLabel"
                @click="toggleRegistrationSortDirection"
              >
                <img :src="registrationDirectionIcon" :alt="registrationDirectionLabel" class="h-6 w-6" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <p v-if="registrationStore.isLoadingMyRegistrations" role="status">
        Loading your registered events…
      </p>
      <p v-else-if="registrationStore.myRegistrationsError" role="alert">
        {{ registrationStore.myRegistrationsError }}
      </p>
      <BauhausEmptyState
        v-else-if="registrationStore.myRegistrations.length === 0"
        title="No registered events yet"
        detail="Events you register or waitlist for will appear here."
      />
      <BauhausEmptyState
        v-else-if="!filteredRegistrations.length"
        :title="registrationSearch || registrationStatuses.length ? 'No matching registrations' : 'No events in this time period'"
        detail="Change the filters or clear them to see your events."
      />
      <div v-else class="space-y-8">
        <section
          v-for="group in eventGroups"
          :key="group.key"
          :data-testid="`${group.key}-registrations`"
          :aria-labelledby="`${group.key}-registrations-title`"
        >
          <div class="mb-4 flex items-center justify-between gap-4">
            <h2 :id="`${group.key}-registrations-title`" class="text-xl font-bold leading-tight">
              {{ group.title }}
            </h2>
            <span class="text-sm font-medium text-ink/70">{{ group.registrations.length }} total</span>
          </div>
          <BauhausEmptyState
            v-if="group.registrations.length === 0"
            :title="`No ${group.key} events`"
          />
          <div v-else class="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            <RouterLink
              v-for="registration in group.registrations"
              :key="registration.id"
              :to="{ name: 'attendee-registered-event', params: { id: registration.event.id } }"
              :data-event-row="registration.event.id"
              :data-tone="registrationCardTone(registration.status)"
              :class="[
                BOARD_CARD_CLASSES,
                BOARD_CARD_TONE_CLASSES[registrationCardTone(registration.status)],
                'block min-w-0',
              ]"
              :aria-label="`Open ${registration.event.name}`"
            >
              <p class="text-sm font-bold">{{ registration.event.name }}</p>
              <p class="text-xs font-bold">{{ registrationStatusLabel(registration.status) }}</p>
              <p class="text-xs text-ink/75">{{ formatRegistrationPeriod(registration.event) }}</p>
              <p v-if="registration.event.venues.length" class="mt-1 text-xs text-ink/75">
                {{ registration.event.venues.map((venue) => venue.name).join(", ") }}
              </p>
            </RouterLink>
          </div>
        </section>
      </div>
    </section>

    <section v-else aria-labelledby="explore-events-heading">
      <div class="mb-8 border-4 border-ink bg-muted p-5 shadow-hard" aria-labelledby="explore-events-heading">
        <h1 id="explore-events-heading" class="mb-5 text-2xl font-bold leading-tight">Explore events</h1>
        <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
          <BauhausInput
            v-model="eventSearch"
            class="w-full sm:min-w-0 sm:flex-[1.4_1_0%]"
            label="Event name"
            placeholder="Search public events"
            aria-label="Search public events"
            compact
          />
          <BauhausSelect
            v-model="eventSortField"
            class="w-full sm:min-w-0 sm:flex-1"
            label="Sort by"
            aria-label="Sort public events by"
            :options="publicEventSortOptions"
            :show-placeholder="false"
            compact
          />
          <button
            type="button"
            class="h-[50px] w-full shrink-0 border-2 border-ink bg-canvas px-3 text-sm font-bold leading-none text-ink shadow-none outline-none transition-colors hover:bg-muted focus:bg-muted sm:w-12"
            :aria-label="`Toggle sort direction, currently ${sortDirectionLabel}`"
            :title="sortDirectionLabel"
            @click="toggleSortDirection"
          >
            <img :src="sortDirectionIcon" :alt="sortDirectionLabel" class="mx-auto h-6 w-6" />
          </button>
        </div>
      </div>

      <p v-if="registrationStore.isLoading" role="status" class="mb-8 text-sm font-bold">
        Loading public events…
      </p>
      <p v-else-if="registrationStore.error" role="alert" class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4">
        {{ registrationStore.error }}
      </p>
      <BauhausEmptyState
        v-else-if="!registrationStore.events.length"
        title="No public events yet"
        detail="Confirmed events will appear here when they are ready to share."
      />
      <BauhausEmptyState
        v-else-if="!visiblePublicEvents.length"
        title="No matching events"
        detail="Change the search or sorting to see another event."
      />
      <div v-else class="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        <PublicEventCard v-for="event in visiblePublicEvents" :key="event.id" :event="event" />
      </div>
    </section>
  </main>
</template>
