<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import EquipmentRequestPanel from "@/components/equipment/EquipmentRequestPanel.vue";
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import CancellationReasonModal from "@/components/events/CancellationReasonModal.vue";
import ChangeRequestChanges from "@/components/events/ChangeRequestChanges.vue";
import EventDiscussion from "@/components/events/EventDiscussion.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import EventStatusProgress from "@/components/events/EventStatusProgress.vue";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";
import { useAuthStore } from "@/stores/auth";
import RejectEventModal from "@/components/events/RejectEventModal.vue";
import ReturnEventModal from "@/components/events/ReturnEventModal.vue";
import { showToast } from "@/composables/useToast";
import { canCancelEvent } from "@/features/events/cancellation";
import { describeChanges } from "@/features/events/changeRequest";
import { canApprove, canReject, canReturn, canSendForSafetyCheck, useEventReviewStore } from "@/features/events/eventReviewStore";
import { formatDecisionTime } from "@/features/venues/bookingDecision";
import SafetyRejectedNotice from "@/components/venues/SafetyRejectedNotice.vue";
import AffectedBookingNotice from "@/components/venues/AffectedBookingNotice.vue";
import ReReviewNotice from "@/components/events/ReReviewNotice.vue";
import { BOOKING_STATUS_LABELS, replacementSearchRoute, venuePanelState } from "@/features/venues/bookingRequest";
import { formatHoldExpiry } from "@/features/venues/dashboard";

const route = useRoute();
const router = useRouter();
const review = useEventReviewStore();
const auth = useAuthStore();

const isSafetyOpen = ref(false);
const isApproveOpen = ref(false);
const isRejectOpen = ref(false);
const isReturnOpen = ref(false);
// Story 115: deciding the organiser's cancellation request, or cancelling directly.
const isApproveCancellationOpen = ref(false);
const isRejectCancellationOpen = ref(false);
const isCancelOpen = ref(false);
// Story 37: deciding the organiser's change request.
const isApproveChangeOpen = ref(false);
const isRejectChangeOpen = ref(false);
// AC7, Q6: a significant change on these events must pass the safety check again.
const approveChangeMessage = computed(() => {
  const request = event.value?.open_change_request;
  const reopens = request?.significant && ["confirmed", "preparation", "safety_review"].includes(event.value.status);
  return reopens
    ? "The new details are applied and the organiser is told. The event goes back to Planning and needs a new safety check."
    : "The new details are applied and the organiser is told.";
});

const event = computed(() => review.event);
const showApprove = computed(() => canApprove(event.value?.status));
const showReject = computed(() => canReject(event.value?.status));
const showReturn = computed(() => canReturn(event.value?.status));
const showCancel = computed(() => canCancelEvent(event.value));
const isReasonOpen = computed(() => isRejectCancellationOpen.value || isCancelOpen.value || isRejectChangeOpen.value);
// CR-97: with spaces, each space card shows its own booking; the panel keeps
// rejections and the reason no venue can be requested yet.
const venuePanel = computed(() => {
  const state = venuePanelState(event.value);
  return eventSpaces.value.length && state.kind !== "unavailable" ? { kind: "none" } : state;
});
// SCRUM-38 AC6, AC7: why venue staff said no, shown above the way to try another venue.
const rejectedBookings = computed(() => event.value?.rejected_bookings ?? []);
const eventSpaces = computed(() => event.value?.spaces ?? []);
// CR-97 AC5: each space's own booking, as the Venue panel reads it.
const spacePanels = computed(() => Object.fromEntries(eventSpaces.value.map((space) => [space.id, venuePanelState(event.value, space)])));

// CR-95 AC4: venue search for this event (or space), asking to replace the affected booking.
function findReplacement(panel, space = null) {
  router.push(replacementSearchRoute(event.value, space, panel.booking));
}

const isAffected = (panel) => panel.kind === "affected" || panel.kind === "replacing";

async function sendForReReview(bookingId, note) {
  try {
    await review.sendBookingForReReview(bookingId, note);
    showToast("Sent to venue staff for re-review");
  } catch {
    // The store exposes the API refusal in the page alert.
  }
}

async function markRevised(bookingId, note) {
  if (review.isActing) return;
  try {
    await review.markBookingRevised(bookingId, note);
    showToast("Marked revised. Send the event for safety check when everything is ready.");
  } catch {
    // The store exposes the API refusal in the page alert.
  }
}

function canFindVenue(space) {
  const panel = spacePanels.value[space.id];
  return panel.kind === "can-request" || (panel.kind === "expired" && panel.canRequest);
}

function displayDateTime(value, timeZone) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat("en-SG", { dateStyle: "full", timeStyle: "short", timeZone }).format(new Date(value));
}

function spaceSchedule(space) {
  const startsAt = space.starts_at ?? event.value?.starts_at;
  const endsAt = space.ends_at ?? event.value?.ends_at;
  if (!startsAt || !endsAt) return "Schedule not provided";
  const prefix = space.starts_at && space.ends_at ? "Schedule" : "Uses event schedule";
  return `${prefix}: ${displayDateTime(startsAt, event.value.event_timezone)} – ${displayDateTime(endsAt, event.value.event_timezone)}`;
}

// A space the booking trigger created has a label only; show what is set.
function spaceRequirements(space) {
  const parts = [space.expected_pax ? `${space.expected_pax} pax` : null, space.layout_preference].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Requirements not specified";
}

function displayValue(value) {
  return value || "Not provided";
}

async function confirmSafety() {
  if (review.isActing) return;
  isSafetyOpen.value = false;
  try {
    await review.sendForSafetyCheck();
    showToast("Sent for safety check");
  } catch {
    // The refreshed readiness and refusal appear in the page.
  }
}

// CR-97 AC9: which space is the primary venue, while the event is in planning.
const canChoosePrimary = computed(() => event.value?.status === "planning" && eventSpaces.value.length > 1);

async function togglePrimary(space) {
  try {
    if (space.is_primary) {
      await review.clearPrimarySpace();
      showToast(`${space.label} is no longer the primary venue`);
    } else {
      await review.setPrimarySpace(space.id);
      showToast(`${space.label} is now the primary venue`);
    }
  } catch {
    // review.error is shown in the page's alert.
  }
}

async function confirmApprove() {
  isApproveOpen.value = false;
  try {
    await review.approve();
    showToast("Request moved to Planning");
  } catch {
    // review.error is shown in the page's alert.
  }
}

async function confirmReject(reason) {
  try {
    await review.reject(reason);
    isRejectOpen.value = false;
    showToast("Request rejected");
  } catch {
    // Kept open so the coordinator sees the error beside their reason.
  }
}

async function confirmReturn({ message, flaggedFields }) {
  try {
    await review.returnForAmendment(message, flaggedFields);
    isReturnOpen.value = false;
    showToast("Returned to organiser");
  } catch {
    // Kept open so the coordinator sees the error beside their message.
  }
}

async function confirmApproveCancellation() {
  isApproveCancellationOpen.value = false;
  try {
    await review.approveCancellation();
    showToast("Event cancelled");
  } catch {
    // review.error is shown in the page's alert.
  }
}

async function confirmRejectCancellation(reason) {
  try {
    await review.rejectCancellation(reason);
    isRejectCancellationOpen.value = false;
    showToast("Cancellation request rejected");
  } catch {
    // Kept open so the coordinator sees the error beside their reason.
  }
}

async function confirmApproveChange() {
  isApproveChangeOpen.value = false;
  try {
    await review.approveChange();
    showToast("Changes approved");
  } catch {
    // review.error is shown in the page's alert.
  }
}

async function confirmRejectChange(reason) {
  try {
    await review.rejectChange(reason);
    isRejectChangeOpen.value = false;
    showToast("Change request rejected");
  } catch {
    // Kept open so the coordinator sees the error beside their reason.
  }
}

async function confirmCancel(reason) {
  try {
    await review.cancelEvent(reason);
    isCancelOpen.value = false;
    showToast("Event cancelled");
  } catch {
    // Kept open so the coordinator sees the error beside their reason.
  }
}

watch(
  () => route.params.id,
  (id) => {
    if (id) review.load(id);
  },
  { immediate: true },
);
</script>

<template>
  <main class="py-8">
    <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <BauhausButton variant="outline" @click="router.push({ name: 'dashboard-coordinator', query: { tab: 'events' } })">Back to events</BauhausButton>
    </div>

    <p
      v-if="review.error && !isRejectOpen && !isReturnOpen && !isReasonOpen"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ review.error }}
    </p>

    <template v-if="event">
      <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-6">
          <div class="min-w-0 flex-1">
            <p class="text-xs font-bold opacity-80">Event request</p>
            <h1 class="mt-2 break-words text-4xl font-bold leading-tight sm:text-5xl">{{ event.name }}</h1>
          </div>
          <div
            v-if="showApprove || showReject || showReturn || showCancel || event.status === 'planning'"
            class="flex flex-wrap gap-3 lg:justify-end"
            data-testid="review-actions"
          >
            <BauhausButton v-if="event.status === 'planning'" variant="secondary" size="sm" aria-label="Send for safety check"
              :disabled="!canSendForSafetyCheck(event) || review.isActing"
              :aria-describedby="event.safety_readiness?.missing.length ? 'safety-missing' : undefined"
              @click="review.error = null; isSafetyOpen = true">Send for safety check</BauhausButton>
            <BauhausButton
              v-if="showApprove"
              size="sm"
              variant="secondary"
              aria-label="Approve request"
              :disabled="review.isActing"
              @click="review.error = null; isApproveOpen = true"
            >
              Approve
            </BauhausButton>
            <BauhausButton
              v-if="showReturn"
              size="sm"
              variant="yellow"
              aria-label="Open return dialog"
              :disabled="review.isActing"
              @click="review.error = null; isReturnOpen = true"
            >
              Ask for amendment
            </BauhausButton>
            <BauhausButton
              v-if="showReject"
              size="sm"
              variant="primary"
              aria-label="Open reject dialog"
              :disabled="review.isActing"
              @click="review.error = null; isRejectOpen = true"
            >
              Reject
            </BauhausButton>
            <BauhausButton
              v-if="showCancel"
              size="sm"
              variant="outline"
              aria-label="Cancel event"
              :disabled="review.isActing"
              @click="review.error = null; isCancelOpen = true"
            >
              Cancel event
            </BauhausButton>
          </div>
        </div>
        <EventStatusProgress :status="event.status" class="mt-6" />
      </BauhausCard>

      <BauhausCard v-if="auth.role === 'event_coordinator' && event.status === 'planning' && event.latest_safety_decision" background="white" accent="none" class="mb-8">
        <h2 class="mb-4 text-2xl font-bold">Safety Officer's decision</h2>
        <SafetyDecisionDetails :decision="event.latest_safety_decision" />
      </BauhausCard>

      <BauhausCard v-if="event.status === 'planning'" background="white" accent="none" class="mb-8">
        <div v-if="event.safety_readiness?.missing.length" id="safety-missing" class="mb-6">
          <h2 class="text-xl font-bold">Not ready for safety check</h2>
          <ul class="mt-3 list-disc pl-5"><li v-for="missing in event.safety_readiness.missing" :key="missing">{{ missing }}</li></ul>
        </div>
        <h2 class="text-xl font-bold">For information</h2>
        <p class="mt-3">Registration: {{ event.registration_enabled ? 'Enabled' : 'Not enabled' }}</p>
        <dl v-if="event.registration_enabled" class="mt-3 grid gap-3 sm:grid-cols-3">
          <div><dt class="font-bold">Capacity</dt><dd>{{ event.registration_capacity ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold">Opens</dt><dd>{{ displayDateTime(event.registration_opens_at, event.event_timezone) }}</dd></div>
          <div><dt class="font-bold">Closes</dt><dd>{{ displayDateTime(event.registration_closes_at, event.event_timezone) }}</dd></div>
        </dl>
      </BauhausCard>
      <AmendmentBanner
        v-if="event.status === 'returned' && event.amendment"
        :amendment="event.amendment"
        audience="coordinator"
        class="mb-8"
      />
      <!-- Story 84 shows the request; story 115 decides it. -->
      <section
        v-if="event.open_cancellation_request"
        data-testid="cancellation-request-banner"
        class="mb-8 border-4 border-ink bg-bauhaus-red p-6 text-canvas shadow-hard sm:p-8"
      >
        <h2 class="text-2xl font-bold">
          Cancellation requested by {{ event.open_cancellation_request.requested_by?.full_name ?? "the organiser" }}
        </h2>
        <p class="mt-4 text-sm font-bold">Comments:</p>
        <p class="mt-1 whitespace-pre-wrap font-medium" data-testid="cancellation-request-comments">{{ event.open_cancellation_request.reason }}</p>
        <p class="mt-4 text-sm font-bold">Arrangements stay held until you decide.</p>
        <div class="mt-6 flex flex-wrap gap-3">
          <BauhausButton size="sm" variant="yellow" aria-label="Approve cancellation" :disabled="review.isActing"
            @click="review.error = null; isApproveCancellationOpen = true">Approve cancellation</BauhausButton>
          <BauhausButton size="sm" variant="outline" aria-label="Reject cancellation" :disabled="review.isActing"
            @click="review.error = null; isRejectCancellationOpen = true">Reject cancellation</BauhausButton>
        </div>
      </section>

      <!-- Story 32 shows the request; story 37 decides it. -->
      <section
        v-if="event.open_change_request"
        data-testid="change-request-banner"
        class="mb-8 border-4 border-ink bg-bauhaus-yellow p-6 shadow-hard sm:p-8"
      >
        <h2 class="text-2xl font-bold">
          Changes requested by {{ event.open_change_request.requested_by?.full_name ?? "the organiser" }}
        </h2>
        <p class="mt-2 inline-block border-2 border-ink bg-canvas px-2 py-1 text-xs font-bold">
          {{ event.open_change_request.significant ? "Significant change" : "Ordinary change" }}
        </p>
        <ChangeRequestChanges :rows="describeChanges(event.open_change_request.changes)" class="mt-4 bg-canvas" />
        <p class="mt-4 text-sm font-bold">Comments:</p>
        <p class="mt-1 whitespace-pre-wrap font-medium" data-testid="change-request-comments">{{ event.open_change_request.reason }}</p>
        <div class="mt-6 flex flex-wrap gap-3">
          <BauhausButton size="sm" variant="secondary" aria-label="Approve changes" :disabled="review.isActing"
            @click="review.error = null; isApproveChangeOpen = true">Approve changes</BauhausButton>
          <BauhausButton size="sm" variant="outline" aria-label="Reject changes" :disabled="review.isActing"
            @click="review.error = null; isRejectChangeOpen = true">Reject changes</BauhausButton>
        </div>
      </section>

      <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <BauhausCard background="white" accent="none" data-testid="request-details-card">
          <h2 class="text-2xl font-bold">Request details</h2>
          <dl class="mt-4 grid gap-4 sm:grid-cols-2">
            <div class="sm:col-span-2"><dt class="text-xs font-bold text-ink/70">Request ID</dt><dd class="mt-2 break-all font-medium" data-testid="request-id">{{ event.id }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Purpose</dt><dd class="mt-2 font-medium">{{ displayValue(event.purpose) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Expected attendance</dt><dd class="mt-2 font-medium">{{ displayValue(event.expected_attendance) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Starts</dt><dd class="mt-2 font-medium">{{ displayDateTime(event.starts_at, event.event_timezone) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Ends</dt><dd class="mt-2 font-medium">{{ displayDateTime(event.ends_at, event.event_timezone) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold text-ink/70">Accessibility needs</dt><dd class="mt-2 font-medium">{{ displayValue(event.accessibility_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold text-ink/70">Equipment needs</dt><dd class="mt-2 font-medium">{{ displayValue(event.preliminary_equipment_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold text-ink/70">Description</dt><dd class="mt-2 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
          </dl>
          <section v-if="eventSpaces.length" class="mt-6 border-t-4 border-ink pt-6" data-testid="event-spaces">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-xl font-bold">Space requests</h3>
              <span class="text-xs font-bold text-ink/70" data-testid="space-count">{{ eventSpaces.length }} {{ eventSpaces.length === 1 ? "space" : "spaces" }}</span>
            </div>
            <div class="mt-4 grid gap-4">
              <article v-for="space in eventSpaces" :key="space.id" class="border-2 border-ink bg-canvas p-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div class="flex flex-wrap items-center gap-2">
                      <h4 class="text-lg font-bold">{{ space.label }}</h4>
                      <span
                        v-if="space.is_primary"
                        class="border-2 border-ink bg-bauhaus-red px-2 py-0.5 text-xs font-bold text-canvas"
                        data-testid="primary-badge"
                      >Primary venue</span>
                    </div>
                    <p class="mt-1 text-sm font-medium" data-testid="space-requirements">{{ spaceRequirements(space) }}</p>
                    <p class="mt-1 text-sm font-medium">{{ spaceSchedule(space) }}</p>
                  </div>
                  <RouterLink
                    v-if="canFindVenue(space)"
                    :to="{ name: 'venue-search', query: { event: event.id, space: space.id } }"
                    class="border-2 border-ink bg-bauhaus-yellow px-3 py-2 text-xs font-bold shadow-hard hover:bg-muted"
                  >
                    Find venue
                  </RouterLink>
                </div>
                <BauhausButton
                  v-if="canChoosePrimary"
                  class="mt-3"
                  variant="outline"
                  :aria-label="space.is_primary ? `Unset ${space.label} as the primary venue` : `Make ${space.label} the primary venue`"
                  :disabled="review.isActing"
                  @click="togglePrimary(space)"
                >
                  {{ space.is_primary ? "Unset primary" : "Make primary" }}
                </BauhausButton>
                <p class="mt-2 text-xs font-bold text-ink/70">{{ space.facilities_required?.length ? space.facilities_required.join(", ") : "No facilities specified" }}</p>
                <div v-if="spacePanels[space.id].booking" class="mt-3 flex flex-wrap items-center gap-3" data-testid="space-booking">
                  <RouterLink
                    :to="{ name: 'venue-detail', params: { id: spacePanels[space.id].booking.venue_id } }"
                    class="font-bold underline decoration-2 underline-offset-4"
                  >
                    {{ spacePanels[space.id].booking.venue_name ?? "Venue" }}
                  </RouterLink>
                  <span
                    class="border-2 border-ink px-2 py-0.5 text-xs font-bold"
                    :class="spacePanels[space.id].booking.status === 'approved' ? 'bg-bauhaus-blue text-canvas' : 'bg-bauhaus-yellow'"
                  >
                    {{ BOOKING_STATUS_LABELS[spacePanels[space.id].booking.status] ?? spacePanels[space.id].booking.status }}
                  </span>
                  <span v-if="spacePanels[space.id].booking.status === 'held' && spacePanels[space.id].booking.expires_at" class="text-sm font-bold">
                    Hold expires {{ formatHoldExpiry(spacePanels[space.id].booking.expires_at) }} unless approved.
                  </span>
                </div>
                <SafetyRejectedNotice
                  v-if="spacePanels[space.id].kind === 'safety-rejected'"
                  :reason="spacePanels[space.id].reason"
                  :can-mark-revised="spacePanels[space.id].canMarkRevised"
                  :busy="review.isActing"
                  @mark-revised="(note) => markRevised(spacePanels[space.id].booking.id, note)"
                  :can-replace="spacePanels[space.id].canReplace"
                  :replacement="spacePanels[space.id].replacement ?? null"
                  @replace="findReplacement(spacePanels[space.id], space)"
                />
                <AffectedBookingNotice
                  v-if="isAffected(spacePanels[space.id])"
                  :reason="spacePanels[space.id].booking.flag_reason ?? ''"
                  :replacement="spacePanels[space.id].replacement ?? null"
                  :can-replace="Boolean(spacePanels[space.id].canReplace)"
                  @replace="findReplacement(spacePanels[space.id], space)"
                />
                <ReReviewNotice
                  v-if="spacePanels[space.id].booking?.needs_re_review_reason"
                  :reason="spacePanels[space.id].booking.needs_re_review_reason"
                  recipients="venue staff"
                  :busy="review.isActing"
                  @send="(note) => sendForReReview(spacePanels[space.id].booking.id, note)"
                />
                <p v-if="spacePanels[space.id].kind === 'expired'" class="mt-2 text-sm font-medium" data-testid="hold-expired">
                  The hold expired on {{ formatHoldExpiry(spacePanels[space.id].booking.expires_at) }} before venue staff approved it.
                  <template v-if="spacePanels[space.id].canRequest">You can request this venue again if it's still free, or find another.</template>
                </p>
              </article>
            </div>
          </section>
          <div class="mt-6 border-t-4 border-ink pt-6">
            <EquipmentRequestPanel :event-id="event.id" :status="event.status" />
          </div>
        </BauhausCard>

        <BauhausCard
          v-if="venuePanel.kind !== 'none' || rejectedBookings.length"
          background="white"
          accent="none"
          data-testid="venue-panel"
        >
          <h2 class="text-2xl font-bold">Venue</h2>
          <ul v-if="rejectedBookings.length" class="mt-4 space-y-4">
            <li v-for="rejected in rejectedBookings" :key="rejected.id" class="border-2 border-ink p-4">
              <p class="text-xs font-bold text-ink/70">Rejected by venue staff</p>
              <p class="mt-1 font-bold">
                <RouterLink :to="{ name: 'booking-request', params: { id: rejected.id } }" class="underline decoration-2 underline-offset-4">
                  {{ rejected.venue_name ?? "Venue" }}
                </RouterLink>
              </p>
              <p v-if="rejected.decided_at" class="text-sm font-medium text-ink/70">{{ formatDecisionTime(rejected.decided_at) }}</p>
              <p class="mt-2 whitespace-pre-wrap text-sm font-medium">{{ rejected.reason ?? "No reason was recorded." }}</p>
              <p v-if="rejected.suggestion" class="mt-2 whitespace-pre-wrap text-sm font-medium">
                <span class="font-bold">Suggested instead:</span> {{ rejected.suggestion }}
              </p>
            </li>
          </ul>
          <template v-if="venuePanel.kind === 'safety-rejected'">
            <p class="mt-4 text-lg font-bold">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <SafetyRejectedNotice
              :reason="venuePanel.reason"
              :can-mark-revised="venuePanel.canMarkRevised"
              :busy="review.isActing"
              @mark-revised="(note) => markRevised(venuePanel.booking.id, note)"
              :can-replace="venuePanel.canReplace"
              :replacement="venuePanel.replacement ?? null"
              @replace="findReplacement(venuePanel)"
            />
          </template>
          <template v-else-if="isAffected(venuePanel)">
            <p class="mt-4 text-lg font-bold">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <AffectedBookingNotice
              :reason="venuePanel.booking.flag_reason ?? ''"
              :replacement="venuePanel.replacement ?? null"
              :can-replace="Boolean(venuePanel.canReplace)"
              @replace="findReplacement(venuePanel)"
            />
          </template>
          <template v-else-if="venuePanel.kind === 'booked'">
            <p class="mt-4 text-lg font-bold">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <p
              class="mt-3 inline-block border-2 border-ink px-3 py-1 text-xs font-bold"
              :class="venuePanel.booking.status === 'approved' ? 'bg-bauhaus-blue text-canvas' : 'bg-bauhaus-yellow'"
            >
              {{ BOOKING_STATUS_LABELS[venuePanel.booking.status] ?? venuePanel.booking.status }}
            </p>
            <p v-if="venuePanel.booking.status === 'held'" class="mt-3 text-sm font-medium">
              Held for this event's time while venue staff decide.
            </p>
            <p
              v-if="venuePanel.booking.status === 'held' && venuePanel.booking.expires_at"
              class="mt-1 text-sm font-bold"
              data-testid="hold-expiry"
            >
              Hold expires {{ formatHoldExpiry(venuePanel.booking.expires_at) }} unless approved.
            </p>
            <ReReviewNotice
              v-if="venuePanel.booking.needs_re_review_reason"
              :reason="venuePanel.booking.needs_re_review_reason"
              recipients="venue staff"
              :busy="review.isActing"
              @send="(note) => sendForReReview(venuePanel.booking.id, note)"
            />
          </template>
          <template v-else-if="venuePanel.kind === 'expired'">
            <p class="mt-4 text-lg font-bold">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <p class="mt-3 inline-block border-2 border-ink bg-canvas px-3 py-1 text-xs font-bold">
              {{ BOOKING_STATUS_LABELS.expired }}
            </p>
            <p class="mt-3 text-sm font-medium" data-testid="hold-expired">
              The hold expired on {{ formatHoldExpiry(venuePanel.booking.expires_at) }} before venue staff approved it.
              <template v-if="venuePanel.canRequest">You can request this venue again if it's still free, or find another.</template>
            </p>
            <BauhausButton
              v-if="venuePanel.canRequest"
              class="mt-4"
              variant="secondary"
              @click="router.push({ name: 'venue-search', query: { event: event.id } })"
            >
              Find a venue
            </BauhausButton>
          </template>
          <template v-else-if="venuePanel.kind === 'can-request'">
            <p class="mt-4 text-sm font-medium">No venue requested yet. Search with this event's requirements and request one.</p>
            <BauhausButton
              class="mt-4"
              variant="secondary"
              @click="router.push({ name: 'venue-search', query: { event: event.id } })"
            >
              Find a venue
            </BauhausButton>
          </template>
          <p v-else-if="venuePanel.reason" class="mt-4 text-sm font-medium">{{ venuePanel.reason }}</p>
        </BauhausCard>

        <BauhausCard v-if="auth.role === 'event_coordinator' && review.safetyDecisions.length" background="white" accent="none">
          <h2 class="mb-4 text-2xl font-bold">Safety decision history</h2>
          <ol class="space-y-4"><li v-for="decision in review.safetyDecisions" :key="decision.id"><SafetyDecisionDetails :decision="decision" /></li></ol>
        </BauhausCard>

        <div class="grid gap-8 lg:col-span-2 lg:grid-cols-3" data-testid="discussion-history-row">
          <BauhausCard background="white" accent="none" class="lg:col-span-2" data-testid="discussion-card">
            <EventDiscussion :event-id="event.id" :status="event.status" />
          </BauhausCard>

          <BauhausCard background="white" accent="none" data-testid="history-card">
            <h2 class="mb-4 text-2xl font-bold">History</h2>
            <EventStatusHistory :entries="review.history" />
          </BauhausCard>
        </div>
      </div>
    </template>

    <p v-else-if="review.isLoading" class="text-sm font-bold text-ink/70">Loading request…</p>

    <ConfirmModal :open="isSafetyOpen" title="Send for safety check?"
      message="The Safety Officer will check the venue and technical arrangements. Venue and equipment can't be requested again while it's in review."
      confirm-label="Send" @confirm="confirmSafety" @stay="isSafetyOpen = false" />
    <ConfirmModal
      :open="isApproveOpen"
      title="Approve this request?"
      message="It moves to Planning so venue and equipment planning can begin. This does not confirm the event."
      confirm-label="Approve"
      cancel-label="Cancel"
      @confirm="confirmApprove"
      @stay="isApproveOpen = false"
    />
    <RejectEventModal
      v-if="event"
      :open="isRejectOpen"
      :event-name="event.name"
      :busy="review.isActing"
      :error="isRejectOpen ? review.error : null"
      @confirm="confirmReject"
      @cancel="isRejectOpen = false"
    />
    <ConfirmModal
      :open="isApproveCancellationOpen"
      title="Approve the cancellation?"
      message="The event is cancelled. Its venue bookings, equipment and registrations are released, and everyone involved is told. This can't be undone."
      confirm-label="Cancel the event"
      cancel-label="Go back"
      @confirm="confirmApproveCancellation"
      @stay="isApproveCancellationOpen = false"
    />
    <CancellationReasonModal
      :open="isRejectCancellationOpen"
      title="Reject the cancellation request?"
      message="The event stays as it is. The organiser will see your reason."
      confirm-label="Reject request"
      confirm-aria-label="Reject cancellation request"
      :busy="review.isActing"
      :error="isRejectCancellationOpen ? review.error : null"
      @confirm="confirmRejectCancellation"
      @cancel="isRejectCancellationOpen = false"
    />
    <ConfirmModal
      :open="isApproveChangeOpen"
      title="Approve the requested changes?"
      :message="approveChangeMessage"
      confirm-label="Approve changes"
      cancel-label="Go back"
      @confirm="confirmApproveChange"
      @stay="isApproveChangeOpen = false"
    />
    <CancellationReasonModal
      :open="isRejectChangeOpen"
      title="Reject the requested changes?"
      message="The event stays as it is. The organiser will see your reason."
      confirm-label="Reject request"
      confirm-aria-label="Reject change request"
      :busy="review.isActing"
      :error="isRejectChangeOpen ? review.error : null"
      @confirm="confirmRejectChange"
      @cancel="isRejectChangeOpen = false"
    />
    <CancellationReasonModal
      :open="isCancelOpen"
      title="Cancel this event?"
      message="Its venue bookings, equipment and registrations are released, and everyone involved is told. The organiser will see your reason. This can't be undone."
      confirm-label="Cancel event"
      confirm-aria-label="Confirm cancel event"
      :busy="review.isActing"
      :error="isCancelOpen ? review.error : null"
      @confirm="confirmCancel"
      @cancel="isCancelOpen = false"
    />
    <ReturnEventModal
      v-if="event"
      :open="isReturnOpen"
      :event-name="event.name"
      :busy="review.isActing"
      :error="isReturnOpen ? review.error : null"
      @confirm="confirmReturn"
      @cancel="isReturnOpen = false"
    />
  </main>
</template>
