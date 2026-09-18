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
import { computed, onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenueCalendar from "@/components/venues/VenueCalendar.vue";
import {
  blockReasonLabel,
  formatEventReference,
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

const holds = computed(() => dashboard.oldestFirstHolds);
const venueRows = computed(() => dashboard.venueStatuses());

const pillClasses = {
  red: "border-2 border-ink bg-bauhaus-red text-canvas",
  yellow: "border-2 border-ink bg-bauhaus-yellow text-ink",
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
 * Shown because holds never expire and age is the only nudge the system gives
 * (BR-R4), and worded neutrally because the customer ruled out review
 * deadlines and SLA timers outright (LC-R4, QA-55, QA-68). This is never
 * styled as overdue.
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

    <div class="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      <BauhausCard
        v-for="tile in tiles"
        :key="tile.key"
        :background="tile.background"
        :accent="tile.accent"
        :accent-color="tile.accentColor"
      >
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">{{ tile.label }}</p>
        <p class="mt-2 text-5xl font-black tracking-tighter">{{ tile.value }}</p>
        <p class="mt-2 text-xs font-medium text-ink/60">{{ tile.detail }}</p>
      </BauhausCard>
    </div>

    <div class="mb-6">
      <VenueCalendar :items="dashboard.calendarItems" :has-settled="dashboard.hasSettled" />
    </div>

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <section aria-labelledby="pending-requests">
        <h2
          id="pending-requests"
          class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl"
        >
          Pending requests
        </h2>
        <p class="mb-4 text-xs font-medium text-ink/60">
          Longest-waiting first. A hold stays until you decide — nothing expires on its own.
        </p>

        <ol v-if="holds.length" class="flex flex-col gap-3">
          <li v-for="hold in holds" :key="hold.id">
            <RouterLink
              :to="{ name: 'booking-request', params: { id: hold.id } }"
              class="flex flex-col gap-2 border-2 border-ink bg-canvas p-4 shadow-hard active-press sm:border-4"
            >
              <div class="flex flex-wrap items-baseline justify-between gap-2">
                <span class="text-base font-black uppercase leading-tight tracking-tighter">
                  {{ hold.venue_name }}
                </span>
                <span class="text-[10px] font-bold uppercase tracking-widest text-ink/55">
                  {{ waitedFor(hold) }}
                </span>
              </div>
              <span class="text-sm font-medium text-ink/75">{{ formatEventReference(hold) }}</span>
              <span class="text-xs font-bold uppercase tracking-widest text-ink/55">
                {{ formatPeriod(hold.period) }}
              </span>
            </RouterLink>
          </li>
        </ol>

        <BauhausEmptyState
          v-else
          :title="dashboard.hasSettled ? 'No requests waiting' : 'Loading your queue'"
          :detail="emptyDetail('Nothing is waiting on your decision right now.')"
        />
      </section>

      <section aria-labelledby="all-venues">
        <h2 id="all-venues" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
          All venues
        </h2>
        <!-- Not "my venues": staff work as one pool and allocation is not
             tracked, so every venue is this person's to manage (AUTH-R5). -->
        <p class="mb-4 text-xs font-medium text-ink/60">
          Venue staff work as one pool, so every venue is yours to manage.
        </p>

        <ul v-if="venueRows.length" class="flex flex-col gap-3">
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
    </div>
  </main>
</template>
