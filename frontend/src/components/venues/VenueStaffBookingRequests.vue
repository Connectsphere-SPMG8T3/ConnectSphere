<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  ALL_BOOKING_STATUSES,
  ALL_VENUE_STATUSES,
  bookingStatusLabel,
  bookingStatusFilterOptions,
  expiryInputBounds,
  expiryInputToIso,
  filterBookingRequests,
  formatEventReference,
  formatHoldExpiry,
  PENDING_BOOKING_STATUS,
  sortBookingRequests,
  waitingDays,
} from "@/features/venues/dashboard";

const props = defineProps({
  dashboard: {
    type: Object,
    required: true,
  },
});

const dashboard = props.dashboard;
const requestStatus = ref(PENDING_BOOKING_STATUS);
const requestVenueId = ref(ALL_VENUE_STATUSES);
const requestSort = ref("event_soonest");
const requestStartDate = ref("");
const requestEndDate = ref("");
const requestStatusOptions = computed(() => bookingStatusFilterOptions(dashboard.bookingRequests));
const requestVenueOptions = computed(() => [
  { value: ALL_VENUE_STATUSES, label: "All venues" },
  ...dashboard.venues.map((venue) => ({ value: venue.id, label: venue.name })),
]);
const requestSortOptions = [
  { value: "event_soonest", label: "Event date: soonest" },
  { value: "event_latest", label: "Event date: latest" },
  { value: "waiting_longest", label: "Waiting: longest" },
  { value: "waiting_shortest", label: "Waiting: shortest" },
];
const visibleRequests = computed(() =>
  sortBookingRequests(
    filterBookingRequests(dashboard.bookingRequests, {
      status: requestStatus.value,
      venueId: requestVenueId.value,
      startDate: requestStartDate.value,
      endDate: requestEndDate.value,
    }),
    requestSort.value,
  ),
);

const editingHoldId = ref(null);
const expiryDraft = ref("");
const expiryBounds = ref({ min: undefined, max: undefined });

function startExpiryChange(hold) {
  const bounds = expiryInputBounds(hold);
  expiryBounds.value = bounds;
  expiryDraft.value = bounds.value;
  dashboard.expiryError = null;
  editingHoldId.value = hold.id;
}

function cancelExpiryChange() {
  editingHoldId.value = null;
  dashboard.expiryError = null;
}

async function saveExpiry(hold) {
  if (await dashboard.changeHoldExpiry(hold.id, expiryInputToIso(expiryDraft.value))) {
    editingHoldId.value = null;
  }
}

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

function requestCardTone(status) {
  if (["rejected", "expired", "cancelled", "released"].includes(status)) return "red";
  if (["held", "re_review"].includes(status)) return "yellow";
  return "blue";
}

function requestCardHoverClass(status) {
  const hoverClasses = {
    red: "hover:bg-bauhaus-red/10 focus-within:bg-bauhaus-red/10",
    yellow: "hover:bg-bauhaus-yellow/10 focus-within:bg-bauhaus-yellow/10",
    blue: "hover:bg-bauhaus-blue/10 focus-within:bg-bauhaus-blue/10",
  };
  return hoverClasses[requestCardTone(status)];
}

function emptyDetail(clearText) {
  if (!dashboard.hasSettled) return "Checking for updates…";
  return dashboard.isAvailable
    ? clearText
    : "The dashboard could not reach the venue service, so nothing is shown rather than a figure it cannot stand behind.";
}
</script>

<template>
  <section aria-labelledby="booking-requests-heading">
    <h2
      id="booking-requests-heading"
      class="mb-1 text-2xl font-bold leading-tight sm:text-3xl"
    >
      Booking requests
    </h2>
    <p class="mb-4 text-xs font-medium text-ink/60">
      Pending requests appear first. Resolved requests remain available for reference.
    </p>

    <!-- CR-95 AC9: a booking whose venue became unavailable stays in the list
         below under its own status, so it is also shown here, where staff can
         find it and restore it once the venue is free again. -->
    <div
      v-if="dashboard.affectedBookings?.length"
      class="mb-6 border-4 border-ink bg-canvas p-4 shadow-hard"
      data-testid="affected-bookings"
    >
      <h3 class="text-sm font-bold text-bauhaus-red">Venue unavailable</h3>
      <p class="mt-1 text-xs font-medium text-ink/70">
        These bookings are flagged because their venue became unavailable. Open one to restore it once the venue is free.
      </p>
      <ul class="mt-3 space-y-2">
        <li v-for="booking in dashboard.affectedBookings" :key="booking.id">
          <RouterLink
            :to="{ name: 'booking-request', params: { id: booking.id } }"
            class="flex flex-wrap items-baseline justify-between gap-2 border-l-4 border-bauhaus-red bg-surface py-2 pl-3 pr-2 active-press"
          >
            <span class="font-bold">{{ booking.event_name || formatEventReference(booking) }}</span>
            <span class="text-xs font-bold text-ink/70">
              {{ booking.venue_name }} · {{ formatPeriod(booking.period) }}
            </span>
          </RouterLink>
        </li>
      </ul>
    </div>

    <div class="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <BauhausSelect v-model="requestStatus" label="Status" :options="requestStatusOptions" :show-placeholder="false" compact />
      <BauhausSelect v-model="requestVenueId" label="Venue" :options="requestVenueOptions" :show-placeholder="false" compact />
      <BauhausSelect v-model="requestSort" label="Sort by" :options="requestSortOptions" compact />
      <BauhausInput v-model="requestStartDate" type="date" label="From date" compact />
      <BauhausInput v-model="requestEndDate" type="date" label="To date" compact />
    </div>

    <ol
      v-if="visibleRequests.length"
      id="booking-requests-list"
      class="grid grid-cols-1 gap-4"
    >
      <li v-for="request in visibleRequests" :key="request.id">
        <BauhausCard
          :background="requestCardTone(request.status)"
          accent="none"
          compact
          allow-overflow
          data-testid="booking-request-card"
          :data-request-status="request.status"
          :class="[requestCardHoverClass(request.status), 'border-4 shadow-none transition duration-150 hover:-translate-y-0.5 focus-within:-translate-y-0.5 motion-reduce:transition-none']"
        >
          <RouterLink
            :to="{ name: 'booking-request', params: { id: request.id } }"
            class="flex flex-col gap-2 active-press"
          >
            <div class="flex flex-wrap items-baseline justify-between gap-4">
              <span class="text-xl font-bold leading-tight">
                {{ request.event_name || formatEventReference(request) }}
              </span>
              <span class="text-xs font-bold text-ink/70">
                {{ request.venue_name }} · {{ bookingStatusLabel(request.status) }}
              </span>
            </div>
            <span class="text-sm font-medium text-ink/75">
              {{ formatPeriod(request.period) }} · {{ request.coordinator_name || request.requested_by_name || "Coordinator unavailable" }}
            </span>
            <span class="text-xs font-bold text-ink/55">
              Waiting {{ waitingDays(request) ?? "—" }} days
            </span>
            <span
              v-if="request.decision_reason || request.suggestion"
              class="border-t-2 border-ink/20 pt-2 text-xs font-medium text-ink/70"
            >
              {{ request.decision_reason || "No decision reason recorded." }}
              <span v-if="request.suggestion"> Suggested alternative: {{ request.suggestion }}</span>
            </span>
          </RouterLink>
          <div
            v-if="request.status === 'held'"
            class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t-2 border-ink/20 pt-3"
          >
            <span class="text-xs font-bold" :data-testid="`hold-expiry-${request.id}`">
              Expires {{ formatHoldExpiry(request.expires_at) ?? "—" }}
            </span>
            <button
              v-if="editingHoldId !== request.id"
              type="button"
              class="text-xs font-bold underline decoration-2 underline-offset-4"
              @click="startExpiryChange(request)"
            >
              Change
            </button>
          </div>
          <form
            v-if="editingHoldId === request.id"
            class="mt-4 flex flex-col gap-3 border-t-2 border-ink/20 pt-4"
            @submit.prevent="saveExpiry(request)"
          >
            <BauhausInput
              v-model="expiryDraft"
              type="datetime-local"
              label="New expiry (Singapore time)"
              :min="expiryBounds.min"
              :max="expiryBounds.max"
              :error="dashboard.expiryError ?? ''"
              compact
              required
            />
            <p class="text-xs font-medium text-ink/60">Any time before the event starts.</p>
            <div class="flex flex-wrap gap-3">
              <BauhausButton type="submit" variant="secondary" :disabled="dashboard.isChangingExpiry">
                {{ dashboard.isChangingExpiry ? "Saving…" : "Save expiry" }}
              </BauhausButton>
              <BauhausButton variant="outline" :disabled="dashboard.isChangingExpiry" @click="cancelExpiryChange">
                Cancel
              </BauhausButton>
            </div>
          </form>
        </BauhausCard>
      </li>
    </ol>

    <BauhausEmptyState
      v-else
      :title="dashboard.hasSettled ? 'No matching requests' : 'Loading your queue'"
      :detail="emptyDetail('Nothing is waiting on your decision right now. Try changing the request filters.')"
    />
  </section>
</template>
