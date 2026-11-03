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
import { RouterLink, useRouter } from "vue-router";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import SectionHeading from "@/components/common/SectionHeading.vue";
import EventStatusBoard from "@/components/events/EventStatusBoard.vue";
import { sectionTone } from "@/components/common/sectionTone";
import VenueCalendar from "@/components/venues/VenueCalendar.vue";
import { BOARD_CARD_TONE_CLASSES } from "@/features/events/dashboard";
import {
  ALL_BOOKING_STATUSES,
  ALL_VENUE_STATUSES,
  blockReasonLabel,
  bookingStatusColumns,
  formatHoldExpiry,
  filterVenueStatuses,
  formatEventReference,
  venueStatusFilterOptions,
  venueStatusMeta,
  waitingDays,
} from "@/features/venues/dashboard";
import { useVenueStaffDashboardStore } from "@/features/venues/venueStaffDashboardStore";

const dashboard = useVenueStaffDashboardStore();
const router = useRouter();

onMounted(() => dashboard.load());

// AC3: the pending requests and the flagged bookings wait on venue staff, so they are red;
// approved bookings are settled, so they are green.
const columns = computed(() => bookingStatusColumns(dashboard));
const boardTotal = computed(() => columns.value.reduce((total, column) => total + column.events.length, 0));
const CARD_TONES = { flagged: "attention", pending: "attention", approved: "done" };

// A column's title opens the booking requests page: the flagged bookings and the pending
// requests head that page, and the approved ones are a choice in its Status list.
function openStatus(status) {
  router.push({
    name: "dashboard-venue-staff-requests",
    query: status === "approved" ? { status } : {},
  });
}

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
  <main class="py-8">
    <p
      v-if="dashboard.error"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4"
      role="alert"
    >
      {{ dashboard.error }}
    </p>

    <p v-if="!dashboard.hasSettled" role="status" class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-medium shadow-hard sm:border-4">
      Loading bookings...
    </p>
    <section v-else class="mb-10" aria-labelledby="booking-status">
      <div class="mb-4 flex items-baseline justify-between gap-3">
        <SectionHeading id="booking-status" :tone="sectionTone(0)">Booking status</SectionHeading>
        <p class="text-sm font-medium text-ink/70">{{ boardTotal }} total</p>
      </div>

      <EventStatusBoard
        :columns="columns"
        item-key="id"
        :legend="['red', 'green']"
        item-label="bookings"
        @open-status="openStatus"
      >
        <template #card="{ event, column, cardClass }">
          <RouterLink
            :to="{ name: 'booking-request', params: { id: event.id } }"
            :class="[cardClass, BOARD_CARD_TONE_CLASSES[CARD_TONES[column.status]]]"
          >
            <p class="text-sm font-bold">{{ formatEventReference(event) }}</p>
            <p class="text-sm font-medium text-ink/75">{{ event.venue_name }}</p>
            <p class="text-xs text-ink/75">{{ formatPeriod(event.period) }}</p>
            <p v-if="column.status === 'pending'" class="mt-1 text-xs font-bold">
              Expires {{ formatHoldExpiry(event.expires_at) ?? "—" }}
            </p>
            <p
              v-if="column.status === 'flagged' && event.restorable"
              class="mt-1 inline-block border-2 border-ink bg-bauhaus-yellow px-2 py-0.5 text-xs font-bold"
            >
              Venue free again: ready to restore
            </p>
          </RouterLink>
        </template>
      </EventStatusBoard>
    </section>

    <div class="mb-6">
      <VenueCalendar :items="dashboard.calendarItems" :has-settled="dashboard.hasSettled" />
    </div>

    <section aria-labelledby="all-venues">
        <SectionHeading id="all-venues" :tone="sectionTone(2)">All venues</SectionHeading>
        <!-- Not "my venues": staff work as one pool and allocation is not
             tracked, so every venue is this person's to manage (AUTH-R5). -->
        <p class="mb-4 mt-3 text-sm font-medium text-ink/70">
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
            class="border-2 border-ink px-3 py-2 text-sm font-bold active-press"
            :class="activeFilter === option.key ? 'bg-ink text-canvas' : 'bg-canvas text-ink hover:bg-muted'"
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
              class="flex flex-wrap items-center justify-between gap-3 border-2 border-ink bg-canvas p-4 shadow-hard hover:bg-muted active-press sm:border-4"
            >
              <span class="flex flex-col">
                <span class="text-base font-bold leading-tight">
                  {{ row.venue.name }}
                </span>
                <span class="mt-1 text-sm font-medium text-ink/70">{{ venueDetail(row) }}</span>
              </span>
              <span
                class="shrink-0 px-3 py-1 text-sm font-bold"
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
