<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import ManagedRegistrationsPanel from "@/components/registrations/ManagedRegistrationsPanel.vue";
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import EventDiscussion from "@/components/events/EventDiscussion.vue";
import OrganiserVenueList from "@/components/events/OrganiserVenueList.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import ChangeRequestChanges from "@/components/events/ChangeRequestChanges.vue";
import RequestCancellationModal from "@/components/events/RequestCancellationModal.vue";
import { canRequestCancellation } from "@/features/events/cancellation";
import { canRequestChange, describeChanges } from "@/features/events/changeRequest";
import { hasThread } from "@/features/events/comments";
import { coordinatorLabel } from "@/features/events/organiserVenues";
import { BOOKING_STATUS_LABELS } from "@/features/venues/bookingRequest";
import { preparationStageLabel } from "@/features/equipment/preparation";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { useEventReviewStore } from "@/features/events/eventReviewStore";
import { useEventsStore } from "@/stores/events";

const route = useRoute();
const router = useRouter();
const eventsStore = useEventsStore();
const review = useEventReviewStore();
const event = computed(() => eventsStore.events.find((storedEvent) => storedEvent.id === route.params.id));
const statusLabel = computed(() => STATUS_LABELS[event.value?.status] ?? event.value?.status.replaceAll("_", " "));
const rejection = computed(() =>
  event.value?.status === "rejected" ? review.history.find((entry) => entry.to_status === "rejected") ?? null : null,
);

const cancellationOpen = ref(false);
const cancellationBusy = ref(false);
const cancellationError = ref(null);
function formatRequestedAt(at) {
  return at
    ? new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: event.value.eventTimezone }).format(new Date(at))
    : "";
}
const requestedAt = computed(() => formatRequestedAt(event.value?.open_cancellation_request?.requested_at));
const changeRequestedAt = computed(() => formatRequestedAt(event.value?.open_change_request?.requested_at));

function openCancellation() {
  cancellationError.value = null;
  cancellationOpen.value = true;
}

// Story 84: the request is recorded and the page reloads to show it; history is refreshed for AC5.
async function sendCancellation(reason) {
  cancellationBusy.value = true;
  cancellationError.value = null;
  try {
    await eventsStore.requestCancellation(event.value.id, reason);
    cancellationOpen.value = false;
  } catch (error) {
    cancellationError.value = error.message;
    return;
  } finally {
    cancellationBusy.value = false;
  }
  try {
    await review.loadHistory(event.value.id);
  } catch {
    // History is supplementary; the banner already shows the request.
  }
}

function displayDate(value, timeZone) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "full",
    timeZone,
  }).format(new Date(`${value}T12:00:00Z`));
}

function displayDateTime(date, time, timeZone) {
  if (!date || !time) return "Not provided";
  return `${displayDate(date, timeZone)} at ${time}`;
}

function displaySpaceSchedule(space) {
  const startsAt = space.starts_at ?? event.value?.starts_at;
  const endsAt = space.ends_at ?? event.value?.ends_at;
  if (!startsAt || !endsAt) return "Schedule not provided";
  const format = (value) => new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: event.value.eventTimezone,
  }).format(new Date(value));
  const prefix = space.starts_at && space.ends_at ? "Schedule" : "Uses event schedule";
  return `${prefix}: ${format(startsAt)} – ${format(endsAt)}`;
}

function displayValue(value) {
  return value || "Not provided";
}

onMounted(async () => {
  try {
    await eventsStore.get(route.params.id);
  } catch {
    return;
  }
  try {
    await review.loadHistory(route.params.id);
  } catch {
    // History is supplementary; the request details still render without it.
  }
});
</script>

<template>
  <main class="py-8">
    <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <BauhausButton variant="outline" @click="router.push({ name: 'dashboard-organiser', query: { tab: 'events' } })">Back to events</BauhausButton>
      <p v-if="event" class="text-xs font-bold text-ink/70">Request {{ event.id }}</p>
    </div>

    <p
      v-if="eventsStore.error"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ eventsStore.error }}
    </p>

    <template v-if="event">
      <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p class="text-xs font-bold opacity-80">Event request</p>
            <h1 class="mt-2 text-4xl font-bold leading-tight sm:text-5xl">{{ event.name }}</h1>
          </div>
          <p class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold shadow-hard">
            {{ statusLabel }}
          </p>
        </div>
      </BauhausCard>

      <template v-if="['planning', 'safety_review', 'confirmed'].includes(event.status) && event.latest_safety_decision?.reason_label">
        <p class="font-medium" :class="event.latest_safety_decision.organiser_comment ? 'mb-3' : 'mb-8'">{{ event.latest_safety_decision.reason_label }}</p>
        <!-- CR-108 AC5: the officer's comment for the organiser; their private notes never reach this page. -->
        <div v-if="event.latest_safety_decision.organiser_comment" class="mb-8 border-l-4 border-ink pl-3">
          <p class="text-sm font-bold">Comment from the Safety Officer</p>
          <p class="mt-1 whitespace-pre-wrap font-medium">{{ event.latest_safety_decision.organiser_comment }}</p>
        </div>
      </template>
      <p v-if="event.status === 'safety_review'" class="mb-8 font-medium">Your event is with the Safety Officer for its operational safety check.</p>
      <BauhausCard v-if="['confirmed', 'preparation'].includes(event.status)" background="white" accent="none" class="mb-8">
        <h2 class="text-2xl font-bold">Arrangements</h2>
        <template v-if="!event.organiser_venues?.length">
          <p class="mt-4">Venue: {{ event.venue_booking?.venue_name ?? 'Not provided' }}</p>
          <p>Booking: {{ BOOKING_STATUS_LABELS[event.venue_booking?.status] ?? 'Not provided' }}</p>
        </template>
        <p>Technical status: {{ ({ready: 'Ready', not_required: 'Not required', pending: 'Pending', issue: 'Issue'})[event.technical_readiness] ?? 'Not provided' }}</p>
        <!-- CR-110 AC4: the stage only; the API never sends the organiser a note. -->
        <p v-if="event.technical_preparation">Technical preparation: {{ preparationStageLabel(event.technical_preparation.stage) }}</p>
      </BauhausCard>
      <!-- CR-111 AC2 to AC4: each venue separately; the API sends nothing internal. Shown from Planning, so an affected venue is visible there. -->
      <BauhausCard v-if="event.organiser_venues?.length" background="white" accent="none" class="mb-8">
        <OrganiserVenueList :venues="event.organiser_venues" :timezone="event.eventTimezone" />
      </BauhausCard>
      <AmendmentBanner v-if="event.status === 'returned' && event.amendment" :amendment="event.amendment" class="mb-8">
        <BauhausButton variant="primary" @click="router.push({ name: 'event-new', query: { id: event.id } })">Amend and resubmit</BauhausButton>
      </AmendmentBanner>

      <section
        v-if="event.status === 'rejected'"
        data-testid="rejection-notice"
        class="mb-8 border-4 border-ink bg-bauhaus-red p-6 text-canvas shadow-hard sm:p-8"
      >
        <h2 class="text-2xl font-bold">This request was rejected</h2>
        <p v-if="rejection?.reason" class="mt-3 whitespace-pre-wrap font-medium">{{ rejection.reason }}</p>
        <p class="mt-3 text-sm font-bold">It is closed and can't be resubmitted. Start a new request if your plans change.</p>
      </section>

      <section
        v-if="event.open_cancellation_request"
        data-testid="cancellation-request-banner"
        class="mb-8 border-4 border-ink bg-canvas p-6 shadow-hard sm:p-8"
      >
        <h2 class="text-2xl font-bold">Cancellation requested</h2>
        <p class="mt-1 text-xs font-bold text-ink/70">{{ requestedAt }}</p>
        <p class="mt-3 whitespace-pre-wrap font-medium">{{ event.open_cancellation_request.reason }}</p>
        <p class="mt-3 text-sm font-bold">Your arrangements stay in place until your coordinator decides.</p>
      </section>

      <section
        v-if="event.open_change_request"
        data-testid="change-request-banner"
        class="mb-8 border-4 border-ink bg-bauhaus-yellow p-6 shadow-hard sm:p-8"
      >
        <h2 class="text-2xl font-bold">Change requested</h2>
        <p class="mt-1 text-xs font-bold text-ink/70">{{ changeRequestedAt }}</p>
        <ChangeRequestChanges :rows="describeChanges(event.open_change_request.changes)" class="mt-4 bg-canvas" />
        <p class="mt-4 whitespace-pre-wrap font-medium">{{ event.open_change_request.reason }}</p>
        <p class="mt-3 text-sm font-bold">Nothing changes until your coordinator approves the request.</p>
      </section>

      <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">Request details</h2>
          <dl class="mt-6 grid gap-5 sm:grid-cols-2">
            <div><dt class="text-xs font-bold text-ink/70">Purpose</dt><dd class="mt-1 font-medium">{{ displayValue(event.purpose) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Expected attendance</dt><dd class="mt-1 font-medium">{{ displayValue(event.expectedAttendance) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Proposed date</dt><dd class="mt-1 font-medium">{{ displayDate(event.date, event.eventTimezone) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Time</dt><dd class="mt-1 font-medium">{{ displayValue(event.startTime) }}–{{ displayValue(event.endTime) }} ({{ event.eventTimezone }})</dd></div>
            <div v-if="event.spaces?.length" class="sm:col-span-2">
              <dt class="text-xs font-bold text-ink/70">Space requirements</dt>
              <dd class="mt-2 grid gap-2">
                <div v-for="space in event.spaces" :key="space.id" class="border-2 border-ink bg-canvas p-3 font-medium">
                  <strong>{{ space.label }}</strong>: {{ space.expectedPax }} pax · {{ space.layoutPreference || "No layout" }} · {{ space.facilitiesRequired?.length ? space.facilitiesRequired.join(", ") : "No facilities" }}<br />{{ displaySpaceSchedule(space) }}
                </div>
              </dd>
            </div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold text-ink/70">Description</dt><dd class="mt-1 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Accessibility needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.accessibilityNeeds) }}</dd></div>
            <div><dt class="text-xs font-bold text-ink/70">Equipment needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.preliminaryEquipmentNeeds) }}</dd></div>
          </dl>
        </BauhausCard>

        <aside class="flex flex-col gap-8">
          <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow">
            <h2 class="text-2xl font-bold">Registration</h2>
            <p class="mt-4 text-sm font-bold">{{ event.registrationEnabled ? "Enabled" : "Not enabled" }}</p>
            <p class="mt-2 text-xs font-bold text-ink/70">{{ event.eventTimezone }}</p>
            <dl v-if="event.registrationEnabled" class="mt-5 grid gap-4 text-sm">
              <div><dt class="font-bold text-ink/70">Capacity</dt><dd class="mt-1 font-medium">{{ displayValue(event.registrationCapacity) }}</dd></div>
              <div><dt class="font-bold text-ink/70">Opens</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.registrationOpensAt?.slice(0, 10), event.registrationOpensAt?.slice(11, 16), event.eventTimezone) }}</dd></div>
              <div><dt class="font-bold text-ink/70">Closes</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.registrationClosesAt?.slice(0, 10), event.registrationClosesAt?.slice(11, 16), event.eventTimezone) }}</dd></div>
            </dl>
          </BauhausCard>
          <BauhausCard background="white" accent="none">
            <h2 class="text-2xl font-bold">Planning status</h2>
            <p class="mt-3 text-sm font-medium">Your request is currently <strong class="">{{ statusLabel }}</strong>.</p>
            <p class="mt-3 text-sm font-medium">Coordinator: {{ coordinatorLabel(event) }}</p>
            <BauhausButton
              v-if="canRequestChange(event)"
              variant="yellow"
              class="mt-6"
              @click="router.push({ name: 'event-request-change', params: { id: event.id } })"
            >
              Request changes
            </BauhausButton>
            <p v-else-if="event.open_cancellation_request" data-testid="change-request-blocked" class="mt-6 text-sm font-medium">
              A cancellation request is open, so changes can't be requested. Ask your coordinator to reject it first.
            </p>
            <BauhausButton v-if="canRequestCancellation(event)" variant="outline" class="mt-6" @click="openCancellation">
              Request cancellation
            </BauhausButton>
          </BauhausCard>
          <BauhausCard background="white" accent="none">
            <h2 class="mb-6 text-2xl font-bold">History</h2>
            <EventStatusHistory :entries="review.history" />
          </BauhausCard>
          <BauhausCard v-if="hasThread(event.status)" background="white" accent="none">
            <EventDiscussion :event-id="event.id" :status="event.status" />
          </BauhausCard>
        </aside>
      </div>
      <ManagedRegistrationsPanel
        :event-id="event.id"
        class="mt-8"
      />
      <RequestCancellationModal
        :open="cancellationOpen"
        :event-name="event.name"
        :busy="cancellationBusy"
        :error="cancellationError"
        @confirm="sendCancellation"
        @cancel="cancellationOpen = false"
      />
    </template>
  </main>
</template>