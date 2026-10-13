<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import EquipmentRequestPanel from "@/components/equipment/EquipmentRequestPanel.vue";
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import EventDiscussion from "@/components/events/EventDiscussion.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";
import { useAuthStore } from "@/stores/auth";
import RejectEventModal from "@/components/events/RejectEventModal.vue";
import ReturnEventModal from "@/components/events/ReturnEventModal.vue";
import { showToast } from "@/composables/useToast";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { canApprove, canReject, canReturn, canSendForSafetyCheck, useEventReviewStore } from "@/features/events/eventReviewStore";
import { formatDecisionTime } from "@/features/venues/bookingDecision";
import { BOOKING_STATUS_LABELS, venuePanelState } from "@/features/venues/bookingRequest";
import { formatHoldExpiry } from "@/features/venues/dashboard";

const route = useRoute();
const router = useRouter();
const review = useEventReviewStore();
const auth = useAuthStore();

const isSafetyOpen = ref(false);
const isApproveOpen = ref(false);
const isRejectOpen = ref(false);
const isReturnOpen = ref(false);

const event = computed(() => review.event);
const statusLabel = computed(() => STATUS_LABELS[event.value?.status] ?? event.value?.status);
const showApprove = computed(() => canApprove(event.value?.status));
const showReject = computed(() => canReject(event.value?.status));
const showReturn = computed(() => canReturn(event.value?.status));
const venuePanel = computed(() => venuePanelState(event.value));
// SCRUM-38 AC6, AC7: why venue staff said no, shown above the way to try another venue.
const rejectedBookings = computed(() => event.value?.rejected_bookings ?? []);
const eventSpaces = computed(() => event.value?.spaces ?? []);

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

watch(
  () => route.params.id,
  (id) => {
    if (id) review.load(id);
  },
  { immediate: true },
);
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <BauhausButton variant="outline" @click="router.push({ name: 'dashboard-coordinator' })">Back to dashboard</BauhausButton>
      <p v-if="event" class="text-xs font-bold uppercase tracking-widest text-ink/70">Request {{ event.id }}</p>
    </div>

    <p
      v-if="review.error && !isRejectOpen && !isReturnOpen"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ review.error }}
    </p>

    <template v-if="event">
      <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event request</p>
            <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ event.name }}</h1>
          </div>
          <p class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-black uppercase tracking-widest shadow-hard">{{ statusLabel }}</p>
        </div>
        <div v-if="showApprove || showReject || showReturn || event.status === 'planning'" class="mt-6 flex flex-wrap gap-3">
          <BauhausButton v-if="event.status === 'planning'" variant="secondary" aria-label="Send for safety check"
            :disabled="!canSendForSafetyCheck(event) || review.isActing"
            :aria-describedby="event.safety_readiness?.missing.length ? 'safety-missing' : undefined"
            @click="review.error = null; isSafetyOpen = true">Send for safety check</BauhausButton>
          <BauhausButton
            v-if="showApprove"
            variant="secondary"
            aria-label="Approve request"
            :disabled="review.isActing"
            @click="review.error = null; isApproveOpen = true"
          >
            Approve
          </BauhausButton>
          <BauhausButton
            v-if="showReturn"
            variant="yellow"
            aria-label="Open return dialog"
            :disabled="review.isActing"
            @click="review.error = null; isReturnOpen = true"
          >
            Return for amendment
          </BauhausButton>
          <BauhausButton
            v-if="showReject"
            variant="primary"
            aria-label="Open reject dialog"
            :disabled="review.isActing"
            @click="review.error = null; isRejectOpen = true"
          >
            Reject
          </BauhausButton>
        </div>
      </BauhausCard>

      <BauhausCard v-if="auth.role === 'event_coordinator' && event.status === 'planning' && event.latest_safety_decision" background="white" accent="none" class="mb-8">
        <h2 class="mb-4 text-2xl font-black uppercase">Safety Officer's decision</h2>
        <SafetyDecisionDetails :decision="event.latest_safety_decision" />
      </BauhausCard>

      <BauhausCard v-if="event.status === 'planning'" background="white" accent="none" class="mb-8">
        <div v-if="event.safety_readiness?.missing.length" id="safety-missing" class="mb-6">
          <h2 class="text-xl font-black uppercase">Not ready for safety check</h2>
          <ul class="mt-3 list-disc pl-5"><li v-for="missing in event.safety_readiness.missing" :key="missing">{{ missing }}</li></ul>
        </div>
        <h2 class="text-xl font-black uppercase">For information</h2>
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

      <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase tracking-tight">Request details</h2>
          <dl class="mt-6 grid gap-5 sm:grid-cols-2">
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Purpose</dt><dd class="mt-1 font-medium">{{ displayValue(event.purpose) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Expected attendance</dt><dd class="mt-1 font-medium">{{ displayValue(event.expected_attendance) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Starts</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.starts_at, event.event_timezone) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Ends</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.ends_at, event.event_timezone) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.accessibility_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Equipment needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.preliminary_equipment_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Description</dt><dd class="mt-1 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
          </dl>
          <section v-if="eventSpaces.length" class="mt-8 border-t-4 border-ink pt-6" data-testid="event-spaces">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-xl font-black uppercase tracking-tight">Space requests</h3>
              <span class="text-xs font-bold uppercase tracking-widest text-ink/70">{{ eventSpaces.length }} spaces</span>
            </div>
            <div class="mt-4 grid gap-4">
              <article v-for="space in eventSpaces" :key="space.id" class="border-2 border-ink bg-canvas p-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 class="text-lg font-black uppercase tracking-tight">{{ space.label }}</h4>
                    <p class="mt-1 text-sm font-medium">{{ space.expected_pax }} pax · {{ space.layout_preference }}</p>
                    <p class="mt-1 text-sm font-medium">{{ spaceSchedule(space) }}</p>
                  </div>
                  <RouterLink
                    v-if="event.status === 'planning'"
                    :to="{ name: 'venue-search', query: { event: event.id, space: space.id } }"
                    class="border-2 border-ink bg-bauhaus-yellow px-3 py-2 text-xs font-black uppercase tracking-widest shadow-hard"
                  >
                    Find venue
                  </RouterLink>
                </div>
                <p class="mt-2 text-xs font-bold uppercase tracking-wide text-ink/70">{{ space.facilities_required?.length ? space.facilities_required.join(", ") : "No facilities specified" }}</p>
              </article>
            </div>
          </section>
        </BauhausCard>

        <BauhausCard
          v-if="venuePanel.kind !== 'none' || rejectedBookings.length"
          background="white"
          accent="none"
          data-testid="venue-panel"
        >
          <h2 class="text-2xl font-black uppercase tracking-tight">Venue</h2>
          <ul v-if="rejectedBookings.length" class="mt-4 space-y-4">
            <li v-for="rejected in rejectedBookings" :key="rejected.id" class="border-2 border-ink p-4">
              <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Rejected by venue staff</p>
              <p class="mt-1 font-black uppercase tracking-tight">
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
          <template v-if="venuePanel.kind === 'booked'">
            <p class="mt-4 text-lg font-black uppercase tracking-tight">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <p
              class="mt-3 inline-block border-2 border-ink px-3 py-1 text-xs font-black uppercase tracking-widest"
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
          </template>
          <template v-else-if="venuePanel.kind === 'expired'">
            <p class="mt-4 text-lg font-black uppercase tracking-tight">
              <RouterLink
                :to="{ name: 'venue-detail', params: { id: venuePanel.booking.venue_id } }"
                class="underline decoration-2 underline-offset-4"
              >
                {{ venuePanel.booking.venue_name ?? "Venue" }}
              </RouterLink>
            </p>
            <p class="mt-3 inline-block border-2 border-ink bg-canvas px-3 py-1 text-xs font-black uppercase tracking-widest">
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
          <p v-else class="mt-4 text-sm font-medium">{{ venuePanel.reason }}</p>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <h2 class="mb-6 text-2xl font-black uppercase tracking-tight">History</h2>
          <EventStatusHistory :entries="review.history" />
        </BauhausCard>

        <BauhausCard v-if="auth.role === 'event_coordinator' && review.safetyDecisions.length" background="white" accent="none">
          <h2 class="mb-6 text-2xl font-black uppercase">Safety decision history</h2>
          <ol class="space-y-6"><li v-for="decision in review.safetyDecisions" :key="decision.id"><SafetyDecisionDetails :decision="decision" /></li></ol>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <EventDiscussion :event-id="event.id" :status="event.status" />
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <EquipmentRequestPanel :event-id="event.id" :status="event.status" />
        </BauhausCard>
      </div>
    </template>

    <p v-else-if="review.isLoading" class="text-sm font-bold uppercase tracking-widest text-ink/70">Loading request…</p>

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
