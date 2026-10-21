<script setup>
/**
 * Event Coordinator dashboard — SCRUM-72.
 *
 * AC1: a prioritised list of requests needing action, requests awaiting an
 *      initial approval/rejection, and newly received client clarification
 *      responses.
 * AC2: the status of each active event.
 *
 * Laid out like the organiser dashboard (SCRUM-71): an Overview and an Events
 * view, picked from the sidebar through `?tab=`. Every figure comes from
 * `GET /events/dashboard/coordinator`, scoped to the events assigned to this
 * coordinator; action kinds whose data the system doesn't hold yet simply never
 * appear, so nothing on this page invents a figure. Every event opens its
 * review page.
 */
import { computed, onMounted, ref, watch } from "vue";
import { useCappedRows } from "@/composables/useCappedRows";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import CoordinatorEventCard from "@/components/events/CoordinatorEventCard.vue";
import EventStatusBoard from "@/components/events/EventStatusBoard.vue";
import SectionHeading from "@/components/common/SectionHeading.vue";
import { sectionTone } from "@/components/common/sectionTone";
import calendarArrowDown from "@/assets/icons/calendar-arrow-down.svg";
import calendarArrowUp from "@/assets/icons/calendar-arrow-up.svg";
import arrowDownZa from "@/assets/icons/arrow-down-z-a.svg";
import arrowUpAz from "@/assets/icons/arrow-up-a-z.svg";
import {
  ACTION_BADGE_CLASSES,
  ACTIVE_COORDINATOR_STATUSES,
  BOARD_CARD_TONE_CLASSES,
  STATUS_LABELS,
  actionKindMeta,
  boardEventTone,
  flagLabel,
  formatEventDateTime,
  orderBoardEvents,
} from "@/features/events/dashboard";
import {
  coordinatorEventCards,
  filterCoordinatorEvents,
  groupCoordinatorEvents,
  rejectedEventCards,
  sortCoordinatorEvents,
} from "@/features/events/coordinatorDashboard";
import { useCoordinatorDashboardStore } from "@/features/events/store";

const dashboard = useCoordinatorDashboardStore();
const router = useRouter();
const route = useRoute();

const activeTab = computed(() => (route.query.tab === "events" ? "events" : "overview"));

onMounted(() => dashboard.load());

// Until the first load settles no figure can be stood behind, so the page shows
// a loading notice rather than a confident zero (TC-DASH-003).
const isLoaded = computed(() => dashboard.hasSettled && !dashboard.error);

// Every event opens its review page (SCRUM-34/52/33).
const reviewRoute = (eventId) => ({ name: "coordinator-event", params: { id: eventId } });

function openEvents(query) {
  router.push({ name: "dashboard-coordinator", query: { tab: "events", ...query } });
}

// --- Overview ----------------------------------------------------------------


// The Events view's `?action=` filter: AC1's three categories, by label.
const ACTION_CATEGORY_LABELS = {
  immediate: "Immediate action",
  awaitingApproval: "Awaiting approval",
  clarificationResponses: "Clarification responses",
};

// The status board's columns: events needing the coordinator's attention first,
// each tagged with its most urgent action and its card tone, then the rest by
// date. A column holding any such event is flagged so its header turns red.
const boardColumns = computed(() =>
  dashboard.statusGroups.map((group) => {
    const current = group.events.filter((event) => !pastEventIds.value.has(event.event_id));
    const events = orderBoardEvents(current, dashboard.actionItems).map((event) => ({
      ...event,
      tone: boardEventTone(event),
    }));
    return { ...group, events, needsAttention: events.some((event) => event.topAction) };
  }),
);

// Only reached when the API answers 404 — a backend older than this page.
const pendingMessage =
  "The coordinator dashboard endpoint isn't available on this server. This widget shows nothing rather than a placeholder figure.";

function emptyDetail(clearText) {
  return dashboard.isAvailable ? clearText : pendingMessage;
}

// --- Events ------------------------------------------------------------------

const search = ref("");
const status = ref([]);
const sortField = ref("date");
const sortDirection = ref("asc");
const action = computed(() => (ACTION_CATEGORY_LABELS[route.query.action] ? route.query.action : ""));

const statusOptions = ACTIVE_COORDINATOR_STATUSES.map((value) => ({ value, label: STATUS_LABELS[value] }));
const sortOptions = [
  { value: "date", label: "Event date" },
  { value: "name", label: "Event name" },
  { value: "status", label: "Status" },
];
const sortFieldLabels = Object.fromEntries(sortOptions.map((option) => [option.value, option.label]));

watch(
  () => route.query.status,
  (value) => {
    const routeStatuses = Array.isArray(value) ? value : value ? [value] : [];
    status.value = routeStatuses.filter((routeStatus) => ACTIVE_COORDINATOR_STATUSES.includes(routeStatus));
  },
  { immediate: true },
);

const cards = computed(() => coordinatorEventCards(dashboard.activeEvents, dashboard.actionItems));
const visibleCards = computed(() =>
  sortCoordinatorEvents(
    filterCoordinatorEvents(cards.value, { status: status.value, search: search.value, action: action.value }),
    { field: sortField.value, direction: sortDirection.value },
  ),
);
const groupedCards = computed(() => groupCoordinatorEvents(visibleCards.value));

// Past events (confirmed, date gone by) leave the board and both Events columns
// for their own section. The Overview lists every one; the Events view only
// those its filters let through.
const allPastCards = computed(() => groupCoordinatorEvents(cards.value).past);
const pastEventIds = computed(() => new Set(allPastCards.value.map((card) => card.id)));

// Rejected requests are closed and never on the board. The Events view applies
// its search, status and sort to them like any other card.
const rejectedCards = computed(() => rejectedEventCards(dashboard.rejectedEvents));
const visibleRejectedCards = computed(() =>
  sortCoordinatorEvents(
    filterCoordinatorEvents(rejectedCards.value, { status: status.value, search: search.value, action: action.value }),
    { field: sortField.value, direction: sortDirection.value },
  ),
);

// Full-width sections for closed events at the foot of either view.
const closedSections = computed(() => {
  const onEvents = activeTab.value === "events";
  return [
    {
      key: "past-events",
      title: "Past events",
      cards: onEvents ? groupedCards.value.past : allPastCards.value,
      past: true,
      emptyTitle: "No past events",
      emptyDetail: "Confirmed events appear here once their date has passed.",
    },
    {
      key: "rejected-events",
      title: "Rejected events",
      cards: onEvents ? visibleRejectedCards.value : rejectedCards.value,
      past: false,
      emptyTitle: "No rejected events",
      emptyDetail: "Requests you reject appear here.",
    },
  ];
});
const boardTotal = computed(() => dashboard.activeEvents.length - allPastCards.value.length);

const directionIcon = computed(() => {
  if (sortField.value === "date") return sortDirection.value === "asc" ? calendarArrowUp : calendarArrowDown;
  return sortDirection.value === "asc" ? arrowUpAz : arrowDownZa;
});
const directionLabel = computed(
  () => `${sortDirection.value === "asc" ? "Ascending" : "Descending"} by ${sortFieldLabels[sortField.value]}`,
);

function toggleSortDirection() {
  sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
}

function clearFilters() {
  search.value = "";
  status.value = [];
  sortField.value = "date";
  sortDirection.value = "asc";
  router.replace({ query: { ...route.query, status: undefined, action: undefined } });
}

// Each Events column shows four cards before it scrolls, and the Past and
// Rejected lists three (useCappedRows).
const cardLists = ref([]);
const closedLists = ref([]);
useCappedRows(() => cardLists.value, [visibleCards, activeTab, () => dashboard.hasSettled], 4);
useCappedRows(
  () => closedLists.value,
  [visibleCards, visibleRejectedCards, activeTab, () => dashboard.hasSettled],
  3,
);

const cardSections = computed(() => [
  {
    key: "needs-action-events",
    title: "Needs your action",
    cards: groupedCards.value.needsAction,
    emptyTitle: "Nothing waiting on you",
    emptyDetail: "Requests that need your review or a decision will appear here.",
  },
  {
    key: "in-progress-events",
    title: "In progress",
    cards: groupedCards.value.inProgress,
    emptyTitle: "No other events",
    emptyDetail: "Events waiting on the organiser or on arrangements will appear here.",
  },
]);
</script>

<template>
  <main class="py-8">
    <p
      v-if="dashboard.error"
      role="alert"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-medium text-canvas shadow-hard sm:border-4"
    >
      {{ dashboard.error }}
    </p>
    <p
      v-else-if="!dashboard.hasSettled"
      role="status"
      class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-medium shadow-hard sm:border-4"
    >
      Loading events...
    </p>
    <p
      v-else-if="!dashboard.isAvailable"
      class="mb-8 border-2 border-dashed border-ink/40 bg-surface px-5 py-4 text-sm font-medium text-ink/75"
    >
      <span class="font-bold">Awaiting data —</span>
      this server doesn't provide the coordinator dashboard yet, so there is nothing to show.
    </p>

    <!-- Overview -->
    <template v-if="activeTab === 'overview' && isLoaded">
      <section class="mb-10" aria-labelledby="active-events">
        <div class="mb-4 flex items-baseline justify-between gap-3">
          <SectionHeading id="active-events" :tone="sectionTone(0)">Event status</SectionHeading>
          <p class="text-sm font-medium text-ink/70">{{ boardTotal }} total</p>
        </div>

        <EventStatusBoard :columns="boardColumns" @open-status="(status) => openEvents({ status })">
          <template #card="{ event, cardClass }">
            <RouterLink
              :to="reviewRoute(event.event_id)"
              :data-tone="event.tone"
              :class="[cardClass, BOARD_CARD_TONE_CLASSES[event.tone]]"
            >
              <p class="text-sm font-bold">{{ event.event_name }}</p>
              <p class="text-xs text-ink/75">{{ formatEventDateTime(event.starts_at) }}</p>
              <p
                v-if="event.topAction"
                class="mt-1 inline-block border-2 border-ink px-2 py-0.5 text-xs font-medium"
                :class="ACTION_BADGE_CLASSES[actionKindMeta(event.topAction).tone]"
              >
                {{ actionKindMeta(event.topAction).label }}
              </p>
              <p
                v-for="flag in event.flags ?? []"
                :key="flag"
                class="mt-1 inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-medium text-canvas"
              >
                {{ flagLabel(flag) }}
              </p>
            </RouterLink>
          </template>
        </EventStatusBoard>
      </section>

    </template>

    <!-- Events -->
    <template v-if="activeTab === 'events' && isLoaded">
      <section class="border-4 border-ink bg-muted p-5 shadow-hard" aria-labelledby="event-filters">
        <div class="mb-5 flex items-center justify-between gap-4">
          <h2 id="event-filters" class="text-2xl font-bold">Find an event</h2>
          <BauhausButton
            class="shrink-0 px-4 py-2 text-xs shadow-none sm:hidden sm:border-2"
            variant="yellow"
            @click="clearFilters"
          >
            Clear
          </BauhausButton>
        </div>
        <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
          <BauhausInput
            v-model="search"
            class="w-full sm:min-w-0 sm:flex-[1.4_1_0%]"
            label="Event name"
            placeholder="Search by event name"
            aria-label="Search events"
            compact
          />
          <BauhausSelect
            v-model="status"
            class="w-full sm:min-w-0 sm:flex-1"
            label="Status"
            :options="statusOptions"
            aria-label="Filter events by status"
            multiple
            compact
          />
          <div class="flex w-full items-end gap-3 sm:contents">
            <BauhausSelect
              v-model="sortField"
              class="min-w-0 flex-1"
              label="Sort by"
              :options="sortOptions"
              :show-placeholder="false"
              aria-label="Sort events by"
              dropdown
              compact
            />
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
            <BauhausButton class="h-[50px] px-4 py-2 text-xs shadow-none sm:border-2" variant="yellow" @click="clearFilters">
              Clear
            </BauhausButton>
          </div>
        </div>
        <p v-if="action" class="mt-4 text-sm font-medium">
          Showing: {{ ACTION_CATEGORY_LABELS[action] }}
        </p>
      </section>

      <section v-if="!visibleCards.length" class="mt-10">
        <BauhausEmptyState
          :title="cards.length ? 'No matching events' : 'No assigned events'"
          :detail="
            cards.length
              ? 'Clear or change the filters to see another event.'
              : emptyDetail('Events assigned to you will appear here.')
          "
        />
      </section>

      <!-- Needs your action and In progress side by side, stacked on narrow screens. -->
      <div v-else data-card-columns class="mt-10 grid grid-cols-1 items-start gap-10 lg:grid-cols-2 lg:gap-6">
        <section v-for="(section, index) in cardSections" :key="section.key" :aria-labelledby="section.key">
          <div class="mb-5 flex items-center justify-between gap-4">
            <SectionHeading :id="section.key" :tone="sectionTone(index)">{{ section.title }}</SectionHeading>
            <span class="text-sm font-medium text-ink/70">{{ section.cards.length }} total</span>
          </div>
          <ul
            v-if="section.cards.length"
            ref="cardLists"
            data-card-grid
            data-capped-rows
            class="grid grid-cols-1 gap-4 overflow-y-auto pb-2 pr-2"
          >
            <li v-for="card in section.cards" :key="card.id" class="flex">
              <CoordinatorEventCard :card="card" />
            </li>
          </ul>
          <BauhausEmptyState v-else :title="section.emptyTitle" :detail="section.emptyDetail" />
        </section>
      </div>
    </template>

    <!-- Past and rejected events, each full width at the foot of either view. Their
         heading colours continue after the board (Overview) or the two card columns (Events). -->
    <template v-if="isLoaded">
      <section
        v-for="(section, index) in closedSections"
        :key="section.key"
        :class="{ 'mt-10': activeTab === 'events' || index > 0 }"
        :aria-labelledby="section.key"
      >
        <div class="mb-5 flex items-center justify-between gap-4">
          <SectionHeading :id="section.key" :tone="sectionTone(index + (activeTab === 'events' ? 2 : 1))">{{ section.title }}</SectionHeading>
          <span class="text-sm font-medium text-ink/70">{{ section.cards.length }} total</span>
        </div>
        <ul
          v-if="section.cards.length"
          ref="closedLists"
          data-capped-rows
          class="grid grid-cols-1 gap-4 overflow-y-auto pb-2 pr-2"
        >
          <li v-for="card in section.cards" :key="card.id" class="flex">
            <CoordinatorEventCard :card="card" :past="section.past" />
          </li>
        </ul>
        <BauhausEmptyState v-else :title="section.emptyTitle" :detail="section.emptyDetail" />
      </section>
    </template>
  </main>
</template>
