<script setup>
/**
 * One venue booking request. Venue staff see what the event needs from the
 * venue and can approve a held request (SCRUM-36), reject it with a reason
 * (SCRUM-38) or restore an affected one (CR-95); the assigned coordinator
 * reads the same page to see why. Every
 * rule is the API's; this page only avoids offering what it would refuse.
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import RejectBookingModal from "@/components/venues/RejectBookingModal.vue";
import { showToast } from "@/composables/useToast";
import {
  canApproveBooking,
  canRejectBooking,
  canRestoreBooking,
  formatBookingPeriod,
  formatDecisionTime,
  historyActionLabel,
} from "@/features/venues/bookingDecision";
import { useBookingDecisionStore } from "@/features/venues/bookingDecisionStore";
import { bookingStatusLabel } from "@/features/venues/dashboard";
import { FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const auth = useAuthStore();
const store = useBookingDecisionStore();

const isApproveOpen = ref(false);
const isRejectOpen = ref(false);

const LAYOUT_LABELS = Object.fromEntries(LAYOUTS.map((entry) => [entry.value, entry.label]));
const FACILITY_LABELS = Object.fromEntries(FACILITIES.map((entry) => [entry.value, entry.label]));

const booking = computed(() => store.booking);
const event = computed(() => booking.value?.event ?? {});
const showApprove = computed(() => canApproveBooking(booking.value, auth.role));
const showReject = computed(() => canRejectBooking(booking.value, auth.role));
const isDeciding = computed(() => store.isApproving || store.isRejecting);
// CR-95: a booking flagged Affected shows why to everyone who can read the page;
// only venue staff can confirm the venue is free again and restore it (AC9).
const isAffected = computed(() => booking.value?.flag === "affected");
const showRestore = computed(() => canRestoreBooking(booking.value, auth.role));
const facilities = computed(() =>
  (event.value.facilities_required ?? []).map((value) => FACILITY_LABELS[value] ?? value).join(", "),
);
const backLink = computed(() =>
  auth.role === "event_coordinator" && booking.value
    ? { to: { name: "coordinator-event", params: { id: booking.value.event.id } }, label: "Back to event" }
    : { to: { name: "dashboard-venue-staff" }, label: "Back to dashboard" },
);

const notSpecified = (value) => (value === null || value === undefined || value === "" ? "Not specified" : value);

function load() {
  store.error = null;
  store.conflict = false;
  return store.load(String(route.params.id));
}

onMounted(load);
watch(() => route.params.id, (id) => id && load());

function openApprove() {
  store.error = null;
  store.conflict = false;
  isApproveOpen.value = true;
}

async function approve() {
  const ok = await store.approve(String(route.params.id));
  isApproveOpen.value = false;
  if (ok) showToast("Booking approved. The coordinator has been told.");
}

async function restore() {
  const ok = await store.restore(String(route.params.id));
  if (ok) showToast("Booking restored. The coordinator and organiser have been told.");
}

function openReject() {
  store.error = null;
  store.conflict = false;
  isRejectOpen.value = true;
}

async function reject(form) {
  const ok = await store.reject(String(route.params.id), form);
  if (ok) {
    isRejectOpen.value = false;
    showToast("Booking rejected. The coordinator has been told.");
  } else if (store.conflict) {
    isRejectOpen.value = false;
  }
}
</script>

<template>
  <main class="py-8">
    <div class="mb-8">
      <RouterLink
        :to="backLink.to"
        class="inline-block text-xs font-bold underline decoration-2 underline-offset-4"
      >
        ← {{ backLink.label }}
      </RouterLink>
    </div>

    <p v-if="store.isLoading && !booking" data-testid="booking-loading" class="text-sm font-bold">
      Loading…
    </p>

    <BauhausEmptyState v-else-if="store.loadError && !booking" title="Booking not available" :detail="store.loadError" />

    <template v-else-if="booking">
      <p
        v-if="store.conflict && store.error"
        role="alert"
        class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
      >
        {{ store.error }}
      </p>

      <BauhausCard background="yellow" accent="square" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="min-w-0">
            <p class="text-xs font-bold opacity-80">Booking request</p>
            <h1 class="mt-2 break-words text-4xl font-bold leading-tight sm:text-5xl">
              {{ booking.venue_name ?? "Venue" }}
            </h1>
            <p class="mt-3 text-lg font-bold">{{ event.name ?? "Unnamed event" }}</p>
            <p class="mt-1 font-medium">{{ formatBookingPeriod(booking.period) }}</p>
          </div>
          <p class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold shadow-hard">
            {{ bookingStatusLabel(booking.status) }}
          </p>
        </div>
        <div v-if="booking.flag === 'safety_rejected'" class="mt-6 border-l-4 border-bauhaus-red bg-canvas px-4 py-3" data-testid="booking-safety-rejected">
          <p class="text-xs font-bold text-bauhaus-red">Safety rejected</p>
          <p class="mt-1 text-sm font-medium">{{ booking.flag_reason }}</p>
        </div>
        <div v-if="isAffected" class="mt-6 border-l-4 border-bauhaus-red bg-canvas px-4 py-3" data-testid="booking-affected">
          <p class="text-xs font-bold text-bauhaus-red">Affected: venue unavailable</p>
          <p v-if="booking.flag_reason" class="mt-1 text-sm font-medium">{{ booking.flag_reason }}</p>
          <template v-if="showRestore">
            <p class="mt-2 text-sm font-medium">
              If the venue is free again for the whole booking, restore it. The flag is cleared and any replacement
              request is cancelled.
            </p>
            <BauhausButton
              class="mt-3"
              variant="secondary"
              aria-label="Restore original booking"
              :disabled="store.isRestoring"
              @click="restore"
            >
              Restore original booking
            </BauhausButton>
          </template>
        </div>
        <div v-if="showApprove || showReject" class="mt-6 flex flex-wrap gap-3">
          <BauhausButton
            v-if="showApprove"
            variant="secondary"
            aria-label="Approve request"
            :disabled="isDeciding"
            @click="openApprove"
          >
            Approve
          </BauhausButton>
          <BauhausButton
            v-if="showReject"
            variant="primary"
            aria-label="Reject request"
            :disabled="isDeciding"
            @click="openReject"
          >
            Reject
          </BauhausButton>
        </div>
      </BauhausCard>

      <div class="grid gap-8 lg:grid-cols-2">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">What the event needs</h2>
          <dl class="mt-6 grid gap-5 sm:grid-cols-2">
            <div>
              <dt class="text-xs font-bold text-ink/70">Expected attendance</dt>
              <dd class="mt-1 font-medium">{{ notSpecified(event.expected_attendance) }}</dd>
            </div>
            <div>
              <dt class="text-xs font-bold text-ink/70">Layout</dt>
              <dd class="mt-1 font-medium">
                {{ notSpecified(LAYOUT_LABELS[event.layout_preference] ?? event.layout_preference) }}
              </dd>
            </div>
            <div class="sm:col-span-2">
              <dt class="text-xs font-bold text-ink/70">Facilities</dt>
              <dd class="mt-1 font-medium">{{ notSpecified(facilities) }}</dd>
            </div>
            <div class="sm:col-span-2">
              <dt class="text-xs font-bold text-ink/70">Accessibility needs</dt>
              <dd class="mt-1 whitespace-pre-wrap font-medium">{{ notSpecified(event.accessibility_needs) }}</dd>
            </div>
          </dl>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">The request</h2>
          <dl class="mt-6 grid gap-5">
            <div>
              <dt class="text-xs font-bold text-ink/70">Requested by</dt>
              <dd class="mt-1 font-medium">
                {{ booking.requested_by_name ?? "The event's coordinator" }}, {{ formatDecisionTime(booking.requested_at) }}
              </dd>
            </div>
            <div>
              <dt class="text-xs font-bold text-ink/70">Note from the coordinator</dt>
              <dd class="mt-1 whitespace-pre-wrap font-medium">{{ booking.request_note ?? "No note from the coordinator." }}</dd>
            </div>
          </dl>
        </BauhausCard>
      </div>

      <BauhausCard v-if="booking.decision" background="white" accent="none" class="mt-8" data-testid="booking-decision">
        <h2 class="text-2xl font-bold">Rejected by venue staff</h2>
        <p class="mt-2 text-sm font-medium text-ink/70">
          {{ booking.decision.decided_by_name ?? "Venue staff" }}, {{ formatDecisionTime(booking.decision.decided_at) }}
        </p>
        <dl class="mt-6 grid gap-5">
          <div>
            <dt class="text-xs font-bold text-ink/70">Reason</dt>
            <dd class="mt-1 whitespace-pre-wrap font-medium">{{ booking.decision.reason }}</dd>
          </div>
          <div v-if="booking.decision.suggestion">
            <dt class="text-xs font-bold text-ink/70">Suggested alternative</dt>
            <dd class="mt-1 whitespace-pre-wrap font-medium">{{ booking.decision.suggestion }}</dd>
          </div>
        </dl>
      </BauhausCard>

      <BauhausCard background="white" accent="none" class="mt-8" data-testid="booking-history">
        <h2 class="text-2xl font-bold">History</h2>
        <p v-if="!booking.history.length" class="mt-4 text-sm font-medium">No decisions yet.</p>
        <ol v-else class="mt-6 space-y-5">
          <li v-for="(entry, index) in booking.history" :key="index" class="border-l-4 border-ink pl-4">
            <p class="font-bold">{{ historyActionLabel(entry.action) }}</p>
            <p class="text-sm font-medium text-ink/70">
              {{ entry.actor_name ?? "System" }}, {{ formatDecisionTime(entry.at) }}
            </p>
            <p v-if="entry.reason" class="mt-1 whitespace-pre-wrap text-sm font-medium">{{ entry.reason }}</p>
          </li>
        </ol>
      </BauhausCard>
    </template>

    <ConfirmModal
      :open="isApproveOpen"
      title="Approve this booking?"
      :message="`${booking?.venue_name ?? 'This venue'} will be booked for ${event.name ?? 'this event'}, and the coordinator will be told.`"
      confirm-label="Approve"
      cancel-label="Cancel"
      @confirm="approve"
      @stay="isApproveOpen = false"
    />
    <RejectBookingModal
      v-if="booking"
      :open="isRejectOpen"
      :venue-name="booking.venue_name ?? 'this venue'"
      :event-name="event.name ?? 'this event'"
      :busy="store.isRejecting"
      :error="store.conflict ? null : store.error"
      @confirm="reject"
      @cancel="isRejectOpen = false"
    />
  </main>
</template>
