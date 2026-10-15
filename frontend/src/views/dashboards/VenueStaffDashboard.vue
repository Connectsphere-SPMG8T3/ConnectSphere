<script setup>
/**
 * Venue Staff dashboard — SCRUM-70.
 *
 * AC1: venue staff land here on login (handled by ROLE_DASHBOARD_ROUTES).
 * AC2: every venue, with its status at a glance.
 * AC3: the pending booking requests awaiting a decision, across all venues.
 * AC4: active and upcoming blocks.
 * AC5: a venue or a request opens its own page.
 *
 * Every figure below comes from `/venues/dashboard/venue-staff`. Nothing on
 * this page is hardcoded — the three invented metrics that used to live here
 * were defect D8.
 */
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenueCalendar from "@/components/venues/VenueCalendar.vue";
import {
  ALL_BOOKING_STATUSES,
  ALL_VENUE_STATUSES,
  blockReasonLabel,
  filterVenueStatuses,
  formatEventReference,
  venueStatusFilterOptions,
  venueStatusMeta,
  waitingDays,
} from "@/features/venues/dashboard";
import { useVenueStaffDashboardStore } from "@/features/venues/venueStaffDashboardStore";

const dashboard = useVenueStaffDashboardStore();

onMounted(() => dashboard.load());

// Until the first load settles, a count is not something the dashboard can
// stand behind, so it shows an em dash rather than a confident zero.
const show = (value) => (dashboard.hasSettled ? value : "—");

const counts = computed(() => dashboard.counts);

// The four widgets REQUIREMENTS §6.21 asks for, in its priority order. Each
// tile's colour is the one the calendar uses for the same thing, so red means
// blocked, yellow means waiting on a decision, and blue means re-review
// wherever they appear on the page.
const tiles = computed(() => [
  {
    key: "holds",
    label: "Pending requests",
    value: show(counts.value.pendingHolds),
    detail: "Awaiting your approval",
    // The tile counts a list that is further down the same page, so it takes
    // you there. A plain fragment link, not a scroll handler: it works from
    // the keyboard, survives a middle-click, and needs no JavaScript.
    href: "/dashboard/venue-staff/requests",
    background: "yellow",
    accent: "circle",
    accentColor: "bauhaus-red",
  },
  {
    key: "reReview",
    label: "In re-review",
    value: show(counts.value.reReview),
    detail: "Changed after approval",
    background: "blue",
    accent: "square",
    accentColor: "bauhaus-yellow",
  },
  {
    key: "blocks",
    label: "Active & upcoming blocks",
    value: show(counts.value.blocks),
    detail: "Across all venues",
    background: "red",
    accent: "triangle",
    accentColor: "ink",
  },
  {
    key: "venues",
    label: "Venues",
    value: show(counts.value.venuesTotal),
    detail: dashboard.hasSettled
      ? `${counts.value.venuesActive} active · ${counts.value.venuesInactive} inactive`
      : "Loading the catalogue",
    background: "white",
    accent: "none",
  },
]);

// AC2 asks for every venue's status at a glance; with the whole catalogue in
// one panel, "at a glance" needs a way to ask for just the venues in one
// state. The filter is view state, not session state — a reload should show
// the full picture again.
const allVenueRows = computed(() => dashboard.venueStatuses());
const venueFilter = ref(ALL_VENUE_STATUSES);
const filterOptions = computed(() => venueStatusFilterOptions(allVenueRows.value));
// A status can vanish between loads (a block ends, and nothing is blocked any
// more). The control for it goes with it, so fall back to All rather than
// leaving an empty list with nothing on screen explaining why.
const activeFilter = computed(() =>
  filterOptions.value.some((option) => option.key === venueFilter.value)
    ? venueFilter.value
    : ALL_VENUE_STATUSES,
);
const venueRows = computed(() => filterVenueStatuses(allVenueRows.value, activeFilter.value));

// Status badges. Red and yellow are the two that want something from you;
// green is the one that does not, and saying so in colour is faster to scan
// down a list than reading the word. The filter row above deliberately does
// not repeat these colours — which filter you are on is a different question
// from what state a venue is in.
const pillClasses = {
  red: "border-2 border-ink bg-bauhaus-red text-canvas",
  yellow: "border-2 border-ink bg-bauhaus-yellow text-ink",
  green: "border-2 border-ink bg-bauhaus-green text-canvas",
  plain: "border-2 border-ink bg-canvas text-ink",
  muted: "border-2 border-ink bg-muted text-ink/70",
};

// Times are stored in UTC and shown in Asia/Singapore (REQUIREMENTS §4).
const spanFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const timeOnly = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatPeriod(period) {
  if (!period) return "Timing to be confirmed";
  return `${spanFormatter.format(new Date(period.starts_at))}–${timeOnly.format(new Date(period.ends_at))}`;
}

const dayFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  day: "numeric",
  month: "short",
});

const formatDay = (value) => (value ? dayFormatter.format(new Date(value)) : "");

/**
 * How long a request has waited, in words.
 *
 * Worded neutrally because the customer ruled out review deadlines and SLA
 * timers (LC-R4, QA-55, QA-68). The expiry beside it is what now orders the
 * queue (CR-99); age stays as context and is never styled as overdue.
 */
function waitedFor(hold) {
  const days = waitingDays(hold);
  if (days === null) return "";
  if (days === 0) return "Requested today";
  return `Waiting ${days} day${days === 1 ? "" : "s"}`;
}

function venueDetail(row) {
  if (row.status === "blocked") return `Blocked until ${formatDay(row.blockedUntil)}`;
  if (row.status === "block_scheduled") {
    return `${blockReasonLabel(row.reason)} from ${formatDay(row.nextBlockStartsAt)}`;
  }
  if (row.status === "inactive") return "Not bookable";
  return row.venue.location;
}

const unavailableMessage =
  "The dashboard could not reach the venue service, so nothing is shown rather than a figure it cannot stand behind.";

// An empty widget means three different things, and saying which is the point.
function emptyDetail(clearText) {
  if (!dashboard.hasSettled) return "Checking for updates…";
  return dashboard.isAvailable ? clearText : unavailableMessage;
}
</script>

<template>
  <main class="py-12">
    <p
      v-if="dashboard.error"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4"
      role="alert"
    >
      {{ dashboard.error }}
    </p>

    <div class="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
      <!-- Only the one tile that leads anywhere is a link, and it says so on
           hover rather than carrying a standing label: the tiles are read as a
           row of figures, and a permanent instruction on one of them competes
           with the figure it sits under. `group` drives the cue below; the
           shadow on hover and focus is the same one every other clickable card
           on the page uses, so the affordance is not new vocabulary. -->
      <component
        :is="tile.href ? 'a' : 'div'"
        v-for="tile in tiles"
        :key="tile.key"
        :href="tile.href"
        class="block"
        :class="
          tile.href
            ? 'group transition-shadow hover:shadow-hard focus-visible:shadow-hard active-press'
            : ''
        "
      >
        <BauhausSummaryCard
          :label="tile.label"
          :value="tile.value"
          :background="tile.background"
          :accent="tile.accent"
          :accent-color="tile.accentColor"
        >
          <template #detail>
            {{ tile.detail }}
            <!-- Opacity keeps the cue in the accessible name at rest. -->
            <span
              v-if="tile.href"
              class="font-bold uppercase tracking-widest text-ink opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
            >
              See the list ↓
            </span>
          </template>
        </BauhausSummaryCard>
      </component>
    </div>

    <div class="mb-6">
      <VenueCalendar :items="dashboard.calendarItems" :has-settled="dashboard.hasSettled" />
    </div>

    <section aria-labelledby="all-venues">
        <h2 id="all-venues" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
          All venues
        </h2>
        <!-- Not "my venues": staff work as one pool and allocation is not
             tracked, so every venue is this person's to manage (AUTH-R5). -->
        <p class="mb-4 text-xs font-medium text-ink/60">
          Venue staff work as one pool, so every venue is yours to manage.
        </p>

        <div
          v-if="filterOptions.length > 1"
          class="mb-4 flex flex-wrap gap-2"
          role="group"
          aria-label="Filter venues by status"
        >
          <button
            v-for="option in filterOptions"
            :key="option.key"
            type="button"
            class="border-2 border-ink px-3 py-2 text-[10px] font-bold uppercase tracking-widest active-press"
            :class="activeFilter === option.key ? 'bg-ink text-canvas' : 'bg-canvas text-ink'"
            :aria-pressed="activeFilter === option.key"
            @click="venueFilter = option.key"
          >
            {{ option.label }}
            <span class="ml-1 opacity-70">{{ option.count }}</span>
          </button>
        </div>

        <!-- Same cap as the pending list above, for the same reasons. -->
        <ul
          v-if="venueRows.length"
          id="all-venues-list"
          class="flex max-h-[28rem] flex-col gap-3 overflow-y-auto pb-1 pr-1"
        >
          <li v-for="row in venueRows" :key="row.venue.id">
            <RouterLink
              :to="{ name: 'venue-detail', params: { id: row.venue.id } }"
              class="flex flex-wrap items-center justify-between gap-3 border-2 border-ink bg-canvas p-4 shadow-hard active-press sm:border-4"
            >
              <span class="flex flex-col">
                <span class="text-base font-black uppercase leading-tight tracking-tighter">
                  {{ row.venue.name }}
                </span>
                <span class="mt-1 text-xs font-medium text-ink/60">{{ venueDetail(row) }}</span>
              </span>
              <span
                class="shrink-0 px-3 py-1 text-[10px] font-bold uppercase tracking-widest"
                :class="pillClasses[venueStatusMeta(row.status).tone]"
              >
                {{ venueStatusMeta(row.status).label }}
              </span>
            </RouterLink>
          </li>
        </ul>

        <BauhausEmptyState
          v-else
          :title="dashboard.hasSettled ? 'No venues in the catalogue' : 'Loading the catalogue'"
          :detail="emptyDetail('No venues have been added yet.')"
        />
    </section>
  </main>
</template>
