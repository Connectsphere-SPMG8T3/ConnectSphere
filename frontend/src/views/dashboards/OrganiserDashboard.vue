<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import EventStatusBoard from "@/components/events/EventStatusBoard.vue";
import OrganiserBoardCard from "@/components/events/OrganiserBoardCard.vue";
import calendarArrowDown from "@/assets/icons/calendar-arrow-down.svg";
import calendarArrowUp from "@/assets/icons/calendar-arrow-up.svg";
import arrowDownZa from "@/assets/icons/arrow-down-z-a.svg";
import arrowUpAz from "@/assets/icons/arrow-up-a-z.svg";
import {
  filterOrganiserEvents,
  groupOrganiserActiveEvents,
  groupOrganiserClosedEvents,
  getOrganiserAction,
  groupOrganiserEvents,
  needsOrganiserAttention,
  sortOrganiserEvents,
} from "@/features/events/organiserDashboard";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { useEventsStore } from "@/stores/events";

const eventsStore = useEventsStore();
const router = useRouter();
const route = useRoute();
const search = ref("");
const status = ref([]);
const sortField = ref("date");
const sortDirection = ref("asc");
const activeTab = computed(() => (route.query.tab === "events" ? "events" : "overview"));

const statusOptions = [
  "draft",
  "submitted",
  "under_review",
  "returned",
  "planning",
  "safety_review",
  "confirmed",
  "rejected",
  "cancelled",
  "completed",
].map((value) => ({ value, label: STATUS_LABELS[value] }));

const sortOptions = [
  { value: "date", label: "Event date" },
  { value: "name", label: "Event name" },
  { value: "status", label: "Status" },
];

const sortFieldLabels = Object.fromEntries(sortOptions.map((option) => [option.value, option.label]));

const actionMenuEventId = ref(null);

const visibleEvents = computed(() =>
  sortOrganiserEvents(
    filterOrganiserEvents(eventsStore.events, { status: status.value, search: search.value }),
    { field: sortField.value, direction: sortDirection.value },
  ),
);

const groupedEvents = computed(() => groupOrganiserEvents(visibleEvents.value));
const showDraftsSection = computed(() => !status.value.length || status.value.includes("draft"));
const showRequestsSection = computed(() => !status.value.length || status.value.some((value) => value !== "draft"));
const activeEventGroups = computed(() => groupOrganiserActiveEvents(eventsStore.events));
const boardTotal = computed(() => activeEventGroups.value.reduce((total, group) => total + group.events.length, 0));
const closedEvents = computed(() => groupOrganiserClosedEvents(eventsStore.events));
const closedSections = computed(() => [
  {
    key: "past-events",
    title: "Past events",
    events: closedEvents.value.past,
    showStatus: true,
    emptyTitle: "No past events",
    emptyDetail: "Completed events, and confirmed events whose date has passed, appear here.",
  },
  {
    key: "rejected-events",
    title: "Rejected events",
    events: closedEvents.value.rejected,
    showStatus: false,
    emptyTitle: "No rejected events",
    emptyDetail: "Requests ConnectSphere rejects appear here.",
  },
]);
const directionIcon = computed(() => {
  if (sortField.value === "date") return sortDirection.value === "asc" ? calendarArrowUp : calendarArrowDown;
  return sortDirection.value === "asc" ? arrowUpAz : arrowDownZa;
});
const directionLabel = computed(
  () => `${sortDirection.value === "asc" ? "Ascending" : "Descending"} by ${sortFieldLabels[sortField.value]}`,
);

watch(
  () => route.query.status,
  (value) => {
    const routeStatuses = Array.isArray(value) ? value : value ? [value] : [];
    status.value = routeStatuses.filter((routeStatus) => statusOptions.some((option) => option.value === routeStatus));
  },
  { immediate: true },
);

function statusLabel(value) {
  return STATUS_LABELS[value] || value.replaceAll("_", " ");
}

function eventStatusLabel(event) {
  if (event.status === "under_review" && !event.coordinatorId) return "Awaiting assignment";
  return statusLabel(event.status);
}

function formatDate(event) {
  if (!event.date) return "Date not set";
  return new Intl.DateTimeFormat("en-SG", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(`${event.date}T00:00:00`),
  );
}

function formatSchedule(event) {
  if (!event.date) return "Schedule not set";
  const time = event.startTime && event.endTime ? `${event.startTime}-${event.endTime}` : "Time not set";
  return `${formatDate(event)} · ${time} · ${event.eventTimezone}`;
}

function venueName(event) {
  return event.venueName || event.venue_name || "Venue not assigned";
}

function coordinatorAssignment(event) {
  if (!event.coordinatorId && ["submitted", "under_review"].includes(event.status)) return "";
  return event.coordinatorId ? "Coordinator assigned" : "Awaiting assignment";
}

function eventCardTone(status) {
  if (["returned", "rejected", "cancelled"].includes(status)) return "red";
  if (["planning", "completed"].includes(status)) return "yellow";
  return "blue";
}


function eventAction(event) {
  actionMenuEventId.value = null;
  const action = getOrganiserAction(event);
  // Drafts and returned requests are both edited on the request form (SCRUM-33).
  if (action.kind === "continue_draft" || action.kind === "amend") {
    router.push({ name: "event-new", query: { id: event.id } });
    return;
  }
  router.push({ name: "event-detail", params: { id: event.id } });
}

async function cloneEvent(event) {
  actionMenuEventId.value = null;
  const clonedEvent = await eventsStore.clone(event.id);
  router.push({ name: "event-new", query: { id: clonedEvent.id } });
}

function toggleActionMenu(eventId) {
  actionMenuEventId.value = actionMenuEventId.value === eventId ? null : eventId;
}

function clearFilters() {
  search.value = "";
  status.value = [];
  sortField.value = "date";
  sortDirection.value = "asc";
  router.replace({ query: { ...route.query, status: undefined } });
}

function toggleSortDirection() {
  sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
}

function openStatusEvents(groupStatus) {
  router.push({ name: "dashboard-organiser", query: { tab: "events", status: groupStatus } });
}

onMounted(() => eventsStore.load().catch(() => {}));
</script>

<template>
  <main class="py-8">
    <BauhausCard v-if="activeTab === 'events'" background="yellow" accent="none" class="mb-10">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-xs font-bold text-ink/70">My events</p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">
            My event requests
          </h1>
          <p class="mt-3 max-w-2xl text-sm font-medium">
            Search, filter, and open the latest external-safe information for every event you have created.
          </p>
        </div>
        <BauhausButton class="shrink-0 self-start whitespace-nowrap sm:self-center" variant="primary" @click="router.push({ name: 'event-new' })">New event request</BauhausButton>
      </div>
    </BauhausCard>

    <section v-if="activeTab === 'overview'" aria-labelledby="overview-heading">
      <h1 id="overview-heading" class="sr-only">Event organiser dashboard</h1>
      <p v-if="eventsStore.error" role="alert" class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4">{{ eventsStore.error }}</p>
      <p v-else-if="eventsStore.isLoading" role="status" class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-bold shadow-hard sm:border-4">Loading events...</p>
      <template v-else>
        <section class="mb-10" aria-labelledby="my-events-status">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 id="my-events-status" class="text-2xl font-bold leading-tight sm:text-3xl">Event status</h2>
            <div class="flex items-center gap-4">
              <p class="text-sm font-medium text-ink/70">{{ boardTotal }} total</p>
              <BauhausButton class="whitespace-nowrap" variant="primary" aria-label="New event request" @click="router.push({ name: 'event-new' })">+ Request</BauhausButton>
            </div>
          </div>

          <EventStatusBoard :columns="activeEventGroups" item-key="id" @open-status="openStatusEvents">
            <template #card="{ event }">
              <OrganiserBoardCard :event="event" :schedule="formatSchedule(event)" />
            </template>
          </EventStatusBoard>
        </section>

        <!-- Past and rejected events, each full width below the board, as on the coordinator's Overview. -->
        <section
          v-for="section in closedSections"
          :key="section.key"
          class="mb-10"
          :aria-labelledby="section.key"
        >
          <div class="mb-5 flex items-center justify-between gap-4">
            <h2 :id="section.key" class="text-2xl font-bold">{{ section.title }}</h2>
            <span class="text-sm font-medium text-ink/70">{{ section.events.length }} total</span>
          </div>
          <ul v-if="section.events.length" class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <li v-for="event in section.events" :key="event.id" class="flex">
              <OrganiserBoardCard :event="event" :schedule="formatSchedule(event)" :show-status="section.showStatus" />
            </li>
          </ul>
          <BauhausEmptyState v-else :title="section.emptyTitle" :detail="section.emptyDetail" />
        </section>
      </template>
    </section>

    <section v-else class="border-4 border-ink bg-canvas p-5 shadow-hard" aria-labelledby="event-filters">
      <div class="mb-5">
        <div class="flex items-center justify-between gap-4">
          <h2 id="event-filters" class="text-2xl font-bold">Find my event</h2>
          <BauhausButton class="shrink-0 px-4 py-2 text-xs shadow-none sm:border-2 sm:hidden" variant="yellow" @click="clearFilters">Clear</BauhausButton>
        </div>
      </div>
      <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
        <BauhausInput v-model="search" class="w-full sm:min-w-0 sm:flex-[1.4_1_0%]" label="Event name" placeholder="Search by event name" aria-label="Search events" compact />
        <BauhausSelect v-model="status" class="w-full sm:min-w-0 sm:flex-1" label="Status" :options="statusOptions" aria-label="Filter events by status" multiple compact />
        <div class="flex w-full items-end gap-3 sm:contents">
          <BauhausSelect v-model="sortField" class="min-w-0 flex-1" label="Sort by" :options="sortOptions" :show-placeholder="false" aria-label="Sort events by" dropdown compact />
          <button
            type="button"
            class="h-[50px] w-12 shrink-0 border-2 border-ink bg-canvas px-3 text-lg font-bold leading-none text-ink shadow-none outline-none transition-colors hover:bg-muted focus:bg-muted"
            :aria-label="`Toggle sort direction, currently ${directionLabel}`"
            :title="directionLabel"
            @click="toggleSortDirection"
          >
            <img :src="directionIcon" :alt="directionLabel" class="h-6 w-6" />
          </button>
        </div>
        <div class="hidden w-full items-end gap-3 sm:flex sm:w-auto">
          <BauhausButton class="h-[50px] px-4 py-2 text-xs shadow-none sm:border-2" variant="yellow" @click="clearFilters">Clear</BauhausButton>
        </div>
      </div>
    </section>

    <p v-if="activeTab === 'events' && eventsStore.isLoading" role="status" class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-bold shadow-hard sm:border-4">Loading events...</p>
    <p v-else-if="activeTab === 'events' && eventsStore.error" role="alert" class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4">{{ eventsStore.error }}</p>

    <section v-if="activeTab === 'events' && !eventsStore.isLoading && !eventsStore.error && !visibleEvents.length" class="mt-10">
      <BauhausEmptyState
        :title="eventsStore.events.length ? 'No matching events' : 'No event requests yet'"
        :detail="eventsStore.events.length ? 'Clear or change the filters to see another event.' : 'Start with a new event request when you are ready.'"
      />
    </section>

    <template v-if="activeTab === 'events' && !eventsStore.isLoading && !eventsStore.error">
      <section v-if="showDraftsSection" class="mt-10" aria-labelledby="drafts-heading">
        <div class="mb-5 flex items-center justify-between gap-4">
          <h2 id="drafts-heading" class="text-2xl font-bold">Drafts</h2>
          <span class="text-sm font-bold">{{ groupedEvents.drafts.length }} total</span>
        </div>
        <div v-if="groupedEvents.drafts.length" class="grid gap-4">
          <BauhausCard v-for="event in groupedEvents.drafts" :key="event.id" :background="eventCardTone(event.status)" accent="none" compact allow-overflow class="border-4 shadow-none hover:bg-muted focus-within:bg-muted transition duration-150 hover:-translate-y-0.5 focus-within:-translate-y-0.5 motion-reduce:transition-none">
            <div class="flex min-w-0 items-center justify-between gap-4">
              <div class="min-w-0" data-event-name>
                <h3 data-event-name class="text-xl font-bold">{{ event.name }}</h3>
                <p class="mt-1 text-xs font-bold text-ink/70">Draft · {{ formatSchedule(event) }}</p>
                <p class="mt-2 text-sm font-medium">Action needed: finish and submit this request.</p>
              </div>
              <div class="relative flex shrink-0 flex-wrap justify-end gap-2">
                <div class="hidden items-center gap-2 sm:flex">
                  <BauhausButton class="shadow-none transition-colors hover:bg-muted focus:bg-muted" variant="outline" @click="eventAction(event)">Edit draft</BauhausButton>
                  <BauhausButton
                    class="h-[52px] w-[52px] shrink-0 !p-0 shadow-none"
                    variant="outline"
                    :aria-label="`Use ${event.name} as a template`"
                    title="Use as template"
                    @click="cloneEvent(event)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-5 w-5">
                      <rect width="14" height="14" x="8" y="8" rx="2" />
                      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10" />
                    </svg>
                  </BauhausButton>
                </div>
                <div class="sm:hidden">
                  <button
                    type="button"
                    class="h-[52px] w-[52px] border-2 border-ink bg-canvas p-0 text-ink shadow-none transition-colors hover:bg-muted focus:bg-muted"
                    :aria-label="`Open actions for ${event.name}`"
                    :aria-expanded="actionMenuEventId === event.id"
                    aria-haspopup="menu"
                    @click="toggleActionMenu(event.id)"
                    @keydown.esc="actionMenuEventId = null"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class="mx-auto h-5 w-5">
                      <circle cx="5" cy="12" r="2" />
                      <circle cx="12" cy="12" r="2" />
                      <circle cx="19" cy="12" r="2" />
                    </svg>
                  </button>
                  <div v-if="actionMenuEventId === event.id" class="absolute bottom-full right-0 z-10 mb-2 min-w-48 border-2 border-ink bg-canvas p-2 shadow-hard" role="menu">
                    <button type="button" class="block w-full px-3 py-2 text-left text-xs font-bold hover:bg-muted focus:bg-muted" role="menuitem" @click="eventAction(event)">Edit draft</button>
                    <button type="button" class="mt-1 block w-full px-3 py-2 text-left text-xs font-bold hover:bg-muted focus:bg-muted" role="menuitem" @click="cloneEvent(event)">Use as template</button>
                  </div>
                </div>
              </div>
            </div>
          </BauhausCard>
        </div>
        <BauhausEmptyState v-else title="No drafts" detail="Saved drafts will appear here." />
      </section>

      <section v-if="showRequestsSection" class="mt-10" aria-labelledby="requests-heading">
        <div class="mb-5 flex items-center justify-between gap-4">
          <h2 id="requests-heading" class="text-2xl font-bold">Requests</h2>
          <span class="text-sm font-bold">{{ groupedEvents.requests.length }} total</span>
        </div>
        <div v-if="groupedEvents.requests.length" class="grid gap-4">
          <BauhausCard v-for="event in groupedEvents.requests" :key="event.id" :background="eventCardTone(event.status)" accent="none" compact allow-overflow class="border-4 shadow-none hover:bg-muted focus-within:bg-muted transition duration-150 hover:-translate-y-0.5 focus-within:-translate-y-0.5 motion-reduce:transition-none">
            <div class="flex min-w-0 items-center justify-between gap-4">
              <div class="min-w-0" data-event-name>
                <h3 data-event-name class="text-xl font-bold">{{ event.name }}</h3>
                <p class="mt-1 text-xs font-bold text-ink/70">{{ eventStatusLabel(event) }}</p>
                <p class="mt-2 text-sm font-medium">
                  {{ formatSchedule(event) }} · Attendance {{ event.expectedAttendance || 'Not set' }} · {{ venueName(event) }}<span v-if="coordinatorAssignment(event)"> · {{ coordinatorAssignment(event) }}</span>
                </p>
                <p v-if="needsOrganiserAttention(event)" class="mt-2 text-xs font-bold text-bauhaus-red">
                  {{ event.status === 'submitted' && !event.coordinatorId ? 'Action needed: awaiting assignment.' : 'Action needed: review this request.' }}
                </p>
              </div>
              <div class="relative flex shrink-0 flex-wrap justify-end gap-2">
                <div class="hidden items-center gap-2 sm:flex">
                  <BauhausButton class="shadow-none transition-colors hover:bg-muted focus:bg-muted" variant="outline" @click="eventAction(event)">{{ getOrganiserAction(event).label }}</BauhausButton>
                  <BauhausButton
                    class="h-[52px] w-[52px] shrink-0 !p-0 shadow-none"
                    variant="outline"
                    :aria-label="`Use ${event.name} as a template`"
                    title="Use as template"
                    @click="cloneEvent(event)"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-5 w-5">
                      <rect width="14" height="14" x="8" y="8" rx="2" />
                      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10" />
                    </svg>
                  </BauhausButton>
                </div>
                <div class="sm:hidden">
                  <button
                    type="button"
                    class="h-[52px] w-[52px] border-2 border-ink bg-canvas p-0 text-ink shadow-none transition-colors hover:bg-muted focus:bg-muted"
                    :aria-label="`Open actions for ${event.name}`"
                    :aria-expanded="actionMenuEventId === event.id"
                    aria-haspopup="menu"
                    @click="toggleActionMenu(event.id)"
                    @keydown.esc="actionMenuEventId = null"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class="mx-auto h-5 w-5">
                      <circle cx="5" cy="12" r="2" />
                      <circle cx="12" cy="12" r="2" />
                      <circle cx="19" cy="12" r="2" />
                    </svg>
                  </button>
                  <div v-if="actionMenuEventId === event.id" class="absolute bottom-full right-0 z-10 mb-2 min-w-48 border-2 border-ink bg-canvas p-2 shadow-hard" role="menu">
                    <button type="button" class="block w-full px-3 py-2 text-left text-xs font-bold hover:bg-muted focus:bg-muted" role="menuitem" @click="eventAction(event)">{{ getOrganiserAction(event).label }}</button>
                    <button type="button" class="mt-1 block w-full px-3 py-2 text-left text-xs font-bold hover:bg-muted focus:bg-muted" role="menuitem" @click="cloneEvent(event)">Use as template</button>
                  </div>
                </div>
              </div>
            </div>
          </BauhausCard>
        </div>
        <BauhausEmptyState v-else title="No submitted requests" detail="Submitted event requests will appear here." />
      </section>
    </template>
  </main>
</template>
