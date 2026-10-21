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
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import calendarArrowDown from "@/assets/icons/calendar-arrow-down.svg";
import calendarArrowUp from "@/assets/icons/calendar-arrow-up.svg";
import arrowDownZa from "@/assets/icons/arrow-down-z-a.svg";
import arrowUpAz from "@/assets/icons/arrow-up-a-z.svg";
import {
  ACTIVE_COORDINATOR_STATUSES,
  STATUS_LABELS,
  actionKindMeta,
  outstandingReadiness,
  summariseActionItems,
} from "@/features/events/dashboard";
import {
  coordinatorEventCards,
  filterCoordinatorEvents,
  groupCoordinatorEvents,
  sortCoordinatorEvents,
} from "@/features/events/coordinatorDashboard";
import { useCoordinatorDashboardStore } from "@/features/events/store";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const dashboard = useCoordinatorDashboardStore();
const router = useRouter();
const route = useRoute();

const activeTab = computed(() => (route.query.tab === "events" ? "events" : "overview"));

onMounted(() => dashboard.load());

// Until the first load settles no figure can be stood behind, so the page shows
// a loading notice rather than a confident zero (TC-DASH-003).
const isLoaded = computed(() => dashboard.hasSettled && !dashboard.error);

// Times are stored in UTC and shown in Asia/Singapore (REQUIREMENTS §4).
const dateFormat = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

function formatDate(value) {
  if (!value) return "Date to be confirmed";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Date to be confirmed" : dateFormat.format(parsed);
}

// Every event opens its review page (SCRUM-34/52/33).
const reviewRoute = (eventId) => ({ name: "coordinator-event", params: { id: eventId } });

function openEvents(query) {
  router.push({ name: "dashboard-coordinator", query: { tab: "events", ...query } });
}

// --- Overview ----------------------------------------------------------------

const summary = computed(() => summariseActionItems(dashboard.actionItems));
const gaps = computed(() => dashboard.readinessGaps({ days: 14 }));

// AC1's three named categories, each opening the Events view filtered to it.
const ACTION_CATEGORIES = [
  {
    key: "immediate",
    label: "Immediate action",
    background: "red",
    accent: "circle",
    accentColor: "bauhaus-yellow",
    hoverClass: "hover:bg-bauhaus-red/10 focus-within:bg-bauhaus-red/10",
  },
  {
    key: "awaitingApproval",
    label: "Awaiting approval",
    background: "blue",
    accent: "square",
    accentColor: "bauhaus-yellow",
    hoverClass: "hover:bg-bauhaus-blue/10 focus-within:bg-bauhaus-blue/10",
  },
  {
    key: "clarificationResponses",
    label: "Clarification responses",
    background: "yellow",
    accent: "circle",
    accentColor: "bauhaus-red",
    hoverClass: "hover:bg-bauhaus-yellow/10 focus-within:bg-bauhaus-yellow/10",
  },
];
const ACTION_CATEGORY_LABELS = Object.fromEntries(ACTION_CATEGORIES.map((c) => [c.key, c.label]));

const toneClasses = {
  red: "bg-bauhaus-red text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  blue: "bg-bauhaus-blue text-canvas",
};

const STATUS_PAGE_SIZE = 2;
const statusPages = ref({});

function statusPage(status) {
  return statusPages.value[status] || 0;
}

function statusPageCount(eventCount) {
  return Math.ceil(eventCount / STATUS_PAGE_SIZE);
}

function pagedEvents(group) {
  const start = statusPage(group.status) * STATUS_PAGE_SIZE;
  return group.events.slice(start, start + STATUS_PAGE_SIZE);
}

function turnStatusPage(group, delta) {
  const last = statusPageCount(group.events.length) - 1;
  const page = Math.min(last, Math.max(0, statusPage(group.status) + delta));
  statusPages.value = { ...statusPages.value, [group.status]: page };
}

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

// A card takes the colour of what is waiting on it, or of its status when nothing is.
function cardTone(card) {
  if (card.actionKind) return actionKindMeta(card.actionKind).tone;
  return card.status === "planning" ? "yellow" : "blue";
}

const cardHoverClasses = {
  red: "hover:bg-bauhaus-red/10 focus-within:bg-bauhaus-red/10",
  yellow: "hover:bg-bauhaus-yellow/10 focus-within:bg-bauhaus-yellow/10",
  blue: "hover:bg-bauhaus-blue/10 focus-within:bg-bauhaus-blue/10",
};

const cardButtonHoverClasses = {
  red: "transition-colors hover:bg-bauhaus-red/20 focus:bg-bauhaus-red/20",
  yellow: "transition-colors hover:bg-bauhaus-yellow focus:bg-bauhaus-yellow",
  blue: "transition-colors hover:bg-bauhaus-blue/20 focus:bg-bauhaus-blue/20",
};

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
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div v-if="activeTab === 'overview'">
          <p class="text-xs font-bold text-ink/70">Event Coordinator Dashboard</p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">
            Welcome, {{ authStore.profile?.full_name }}
          </h1>
          <p class="mt-3 max-w-2xl text-sm font-medium">
            Your outstanding actions, ranked by what they block, and the status of every event you are
            coordinating.
          </p>
        </div>
        <div v-else>
          <p class="text-xs font-bold text-ink/70">My events</p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">
            Events I'm coordinating
          </h1>
          <p class="mt-3 max-w-2xl text-sm font-medium">
            Search, filter, and open every active event assigned to you.
          </p>
        </div>
        <BauhausButton
          class="shrink-0 self-start whitespace-nowrap sm:self-center"
          variant="primary"
          @click="router.push({ name: 'venue-search' })"
        >
          Search venues
        </BauhausButton>
      </div>
    </BauhausCard>

    <p
      v-if="dashboard.error"
      role="alert"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ dashboard.error }}
    </p>
    <p
      v-else-if="!dashboard.hasSettled"
      role="status"
      class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-bold shadow-hard sm:border-4"
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
      <section class="mb-10" aria-labelledby="needs-action">
        <div class="mb-5 flex items-baseline justify-between gap-4">
          <h2 id="needs-action" class="text-2xl font-bold leading-tight sm:text-3xl">
            Needs your action
          </h2>
          <span class="text-sm font-bold">{{ summary.total }} total</span>
        </div>

        <div class="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          <BauhausSummaryCard
            v-for="category in ACTION_CATEGORIES"
            :key="category.key"
            :aria-label="`Show ${category.label} events`"
            :label="category.label"
            :value="summary[category.key]"
            :background="category.background"
            :accent="category.accent"
            :accent-color="category.accentColor"
            :class="category.hoverClass"
            clickable
            @click="openEvents({ action: category.key })"
          />
        </div>

        <ol v-if="dashboard.prioritisedActions.length" class="space-y-3">
          <li v-for="(item, index) in dashboard.prioritisedActions" :key="`${item.event_id}-${item.kind}`">
            <RouterLink
              :to="reviewRoute(item.event_id)"
              class="flex flex-col gap-3 border-2 border-ink bg-canvas p-5 shadow-hard transition duration-150 hover:-translate-y-0.5 hover:bg-bauhaus-yellow/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink motion-reduce:transition-none sm:flex-row sm:items-center sm:justify-between sm:border-4"
            >
              <div class="flex items-start gap-4">
                <span class="text-2xl font-bold text-ink/30">{{ index + 1 }}</span>
                <div>
                  <p class="text-lg font-bold leading-tight">
                    {{ item.event_name }}
                  </p>
                  <p class="mt-1 text-sm font-medium text-ink/70">
                    {{ actionKindMeta(item.kind).description }}
                  </p>
                  <p class="mt-1 text-xs font-bold text-ink/50">
                    {{ formatDate(item.starts_at) }}
                    <template v-if="item.organiser_name"> · {{ item.organiser_name }}</template>
                  </p>
                </div>
              </div>
              <span
                class="shrink-0 self-start border-2 border-ink px-3 py-1 text-xs font-bold sm:self-center"
                :class="toneClasses[actionKindMeta(item.kind).tone]"
              >
                {{ actionKindMeta(item.kind).label }}
              </span>
            </RouterLink>
          </li>
        </ol>

        <BauhausEmptyState
          v-else
          title="No outstanding actions"
          :detail="emptyDetail('Nothing is waiting on you right now.')"
        />
      </section>

      <section class="mb-10" aria-labelledby="active-events">
        <div class="mb-4 flex items-baseline justify-between gap-3">
          <h2 id="active-events" class="text-2xl font-bold leading-tight sm:text-3xl">
            My events by status
          </h2>
          <p class="text-sm font-bold">{{ dashboard.activeEvents.length }} total</p>
        </div>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div
            v-for="group in dashboard.statusGroups"
            :key="group.status"
            :data-status-group="group.status"
            class="group relative min-h-[220px] border-2 border-ink bg-canvas px-4 pb-4 pt-2 shadow-hard transition duration-150 hover:-translate-y-0.5 hover:bg-bauhaus-yellow/10 focus-within:-translate-y-0.5 focus-within:bg-bauhaus-yellow/10 motion-reduce:transition-none sm:border-4 sm:px-5 sm:pb-5 sm:pt-3"
          >
            <div class="flex items-baseline justify-between gap-3">
              <button
                type="button"
                class="text-left text-xs font-bold underline decoration-2 underline-offset-4 transition-colors hover:text-bauhaus-red focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                :aria-label="`View all ${group.label} events`"
                @click="openEvents({ status: group.status })"
              >
                {{ group.label }}
              </button>
              <p class="text-3xl font-bold">{{ group.events.length }}</p>
            </div>
            <p class="mt-1 text-xs font-medium text-ink/60">{{ group.description }}</p>

            <ul v-if="group.events.length" class="mt-4 space-y-2">
              <li v-for="event in pagedEvents(group)" :key="event.event_id" class="flex">
                <RouterLink
                  :to="reviewRoute(event.event_id)"
                  class="w-full border-l-4 border-ink bg-surface py-2 pl-3 text-left transition-colors hover:bg-bauhaus-yellow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
                >
                  <p class="text-sm font-bold">{{ event.event_name }}</p>
                  <p class="text-xs font-medium text-ink/60">{{ formatDate(event.starts_at) }}</p>
                  <p
                    v-for="flag in event.flags ?? []"
                    :key="flag"
                    class="mt-1 inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-bold text-canvas"
                  >
                    {{ flag.replace(/_/g, " ") }}
                  </p>
                </RouterLink>
              </li>
            </ul>

            <div
              v-if="group.events.length > STATUS_PAGE_SIZE"
              class="absolute bottom-5 right-5 flex items-center gap-1"
            >
              <button
                type="button"
                class="h-6 w-6 border border-ink bg-canvas p-0 text-sm font-bold leading-none shadow-none disabled:cursor-not-allowed disabled:opacity-30"
                :aria-label="`Previous ${group.label} events page`"
                :disabled="statusPage(group.status) === 0"
                @click="turnStatusPage(group, -1)"
              >
                &lt;
              </button>
              <span class="min-w-8 text-center text-xs font-bold">
                {{ statusPage(group.status) + 1 }} / {{ statusPageCount(group.events.length) }}
              </span>
              <button
                type="button"
                class="h-6 w-6 border border-ink bg-canvas p-0 text-sm font-bold leading-none shadow-none disabled:cursor-not-allowed disabled:opacity-30"
                :aria-label="`Next ${group.label} events page`"
                :disabled="statusPage(group.status) >= statusPageCount(group.events.length) - 1"
                @click="turnStatusPage(group, 1)"
              >
                &gt;
              </button>
            </div>

            <p v-if="!group.events.length" class="mt-4 text-sm font-medium text-ink/50">None.</p>
          </div>
        </div>
      </section>

      <section class="mb-10" aria-labelledby="readiness">
        <div class="mb-4 flex items-baseline justify-between gap-3">
          <h2 id="readiness" class="text-2xl font-bold leading-tight sm:text-3xl">
            Readiness gaps — next 14 days
          </h2>
          <p class="text-sm font-bold">{{ gaps.length }} total</p>
        </div>

        <ul v-if="gaps.length" class="grid gap-4">
          <li v-for="event in gaps" :key="event.event_id">
            <RouterLink
              :to="reviewRoute(event.event_id)"
              class="block border-4 border-ink bg-canvas p-4 transition duration-150 hover:-translate-y-0.5 hover:bg-bauhaus-yellow/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink motion-reduce:transition-none sm:p-5"
            >
              <p class="text-xl font-bold">{{ event.event_name }}</p>
              <p class="mt-1 text-xs font-bold text-ink/70">
                {{ formatDate(event.starts_at) }} · {{ STATUS_LABELS[event.status] }}
              </p>
              <p class="mt-2 text-xs font-bold text-bauhaus-red">
                Outstanding: {{ outstandingReadiness(event).join(", ") }}
              </p>
            </RouterLink>
          </li>
        </ul>

        <BauhausEmptyState
          v-else
          title="No readiness gaps"
          :detail="
            emptyDetail('Every event starting in the next 14 days has its blocking arrangements in place.')
          "
        />
      </section>
    </template>

    <!-- Events -->
    <template v-if="activeTab === 'events' && isLoaded">
      <section class="border-4 border-ink bg-canvas p-5 shadow-hard" aria-labelledby="event-filters">
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
              class="h-[50px] w-12 shrink-0 border-2 border-ink bg-canvas px-3 text-lg font-bold leading-none text-ink shadow-none outline-none transition-colors hover:bg-bauhaus-yellow/20 focus:bg-bauhaus-yellow/20"
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
        <p v-if="action" class="mt-4 text-xs font-bold">
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

      <template v-else>
        <section v-for="section in cardSections" :key="section.key" class="mt-10" :aria-labelledby="section.key">
          <div class="mb-5 flex items-center justify-between gap-4">
            <h2 :id="section.key" class="text-2xl font-bold">{{ section.title }}</h2>
            <span class="text-sm font-bold">{{ section.cards.length }} total</span>
          </div>
          <div v-if="section.cards.length" class="grid gap-4">
            <BauhausCard
              v-for="card in section.cards"
              :key="card.id"
              data-event-card
              :background="cardTone(card)"
              accent="none"
              compact
              :class="[
                cardHoverClasses[cardTone(card)],
                'border-4 shadow-none transition duration-150 hover:-translate-y-0.5 focus-within:-translate-y-0.5 motion-reduce:transition-none',
              ]"
            >
              <div class="flex min-w-0 items-center justify-between gap-4">
                <div class="min-w-0">
                  <h3 class="text-xl font-bold">{{ card.name }}</h3>
                  <p class="mt-1 text-xs font-bold text-ink/70">
                    {{ STATUS_LABELS[card.status] }} · {{ formatDate(card.startsAt) }}
                  </p>
                  <p class="mt-2 text-sm font-medium">
                    {{
                      card.outstanding.length
                        ? `Outstanding: ${card.outstanding.join(", ")}`
                        : "All blocking arrangements in place"
                    }}
                  </p>
                  <p v-if="card.actionKind" class="mt-2 text-xs font-bold text-bauhaus-red">
                    Action needed: {{ actionKindMeta(card.actionKind).label }}
                  </p>
                  <p
                    v-for="flag in card.flags"
                    :key="flag"
                    class="mt-2 inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-bold text-canvas"
                  >
                    {{ flag.replace(/_/g, " ") }}
                  </p>
                </div>
                <BauhausButton
                  :class="['shrink-0 shadow-none', cardButtonHoverClasses[cardTone(card)]]"
                  variant="outline"
                  :aria-label="`Review ${card.name}`"
                  @click="router.push(reviewRoute(card.id))"
                >
                  Review
                </BauhausButton>
              </div>
            </BauhausCard>
          </div>
          <BauhausEmptyState v-else :title="section.emptyTitle" :detail="section.emptyDetail" />
        </section>
      </template>
    </template>
  </main>
</template>
