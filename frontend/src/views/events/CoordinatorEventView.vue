<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import RejectEventModal from "@/components/events/RejectEventModal.vue";
import ReturnEventModal from "@/components/events/ReturnEventModal.vue";
import { showToast } from "@/composables/useToast";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { canApprove, canReject, canReturn, useEventReviewStore } from "@/features/events/eventReviewStore";

const route = useRoute();
const router = useRouter();
const review = useEventReviewStore();

const isApproveOpen = ref(false);
const isRejectOpen = ref(false);
const isReturnOpen = ref(false);

const event = computed(() => review.event);
const statusLabel = computed(() => STATUS_LABELS[event.value?.status] ?? event.value?.status);
const showApprove = computed(() => canApprove(event.value?.status));
const showReject = computed(() => canReject(event.value?.status));
const showReturn = computed(() => canReturn(event.value?.status));

function displayDateTime(value, timeZone) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat("en-SG", { dateStyle: "full", timeStyle: "short", timeZone }).format(new Date(value));
}

function displayValue(value) {
  return value || "Not provided";
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
        <div v-if="showApprove || showReject || showReturn" class="mt-6 flex flex-wrap gap-3">
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
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Preferred layout</dt><dd class="mt-1 font-medium">{{ displayValue(event.layout_preference) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Facilities</dt><dd class="mt-1 font-medium">{{ event.facilities_required?.length ? event.facilities_required.join(", ") : "None specified" }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.accessibility_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Equipment needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.preliminary_equipment_needs) }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Description</dt><dd class="mt-1 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
          </dl>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <h2 class="mb-6 text-2xl font-black uppercase tracking-tight">History</h2>
          <EventStatusHistory :entries="review.history" />
        </BauhausCard>
      </div>
    </template>

    <p v-else-if="review.isLoading" class="text-sm font-bold uppercase tracking-widest text-ink/70">Loading request…</p>

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
