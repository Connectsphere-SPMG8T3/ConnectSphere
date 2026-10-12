<script setup>
/**
 * Venue staff reject a held booking (SCRUM-38): a required reason and an
 * optional suggested alternative, both at most 1000 characters (AC2, AC3).
 * Same shape as RequestVenueModal and RejectEventModal; the wording differs
 * because the coordinator, not the organiser, reads this reason (AC6).
 */
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { REJECTION_TEXT_MAX_LENGTH, rejectionErrors, rejectionPayload } from "@/features/venues/bookingDecision";

const props = defineProps({
  open: { type: Boolean, default: false },
  venueName: { type: String, required: true },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const reason = ref("");
const suggestion = ref("");
const canConfirm = computed(
  () => !props.busy && Object.keys(rejectionErrors({ reason: reason.value, suggestion: suggestion.value })).length === 0,
);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      reason.value = "";
      suggestion.value = "";
    }
  },
);

function confirm() {
  if (canConfirm.value) emit("confirm", rejectionPayload({ reason: reason.value, suggestion: suggestion.value }));
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('cancel')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="reject-booking-title"
        class="max-h-full w-full max-w-lg overflow-y-auto border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="reject-booking-title" class="text-2xl font-black uppercase leading-tight tracking-tight">
          Reject this booking request?
        </h2>
        <p class="mt-4 text-base font-medium">
          The hold on {{ props.venueName }} for "{{ props.eventName }}" will be removed and the time freed for other
          requests. The event's coordinator will see your reason and any suggestion; the organiser won't.
        </p>
        <label for="reject-booking-reason" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">
          Reason (required)
        </label>
        <textarea
          id="reject-booking-reason"
          v-model="reason"
          rows="4"
          :maxlength="REJECTION_TEXT_MAX_LENGTH"
          placeholder="For example: unavailable, unsuitable layout, capacity exceeded"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ reason.length }} / {{ REJECTION_TEXT_MAX_LENGTH }}</p>
        <label for="reject-booking-suggestion" class="mt-4 block text-xs font-bold uppercase tracking-widest text-ink/70">
          Suggested alternative (optional)
        </label>
        <textarea
          id="reject-booking-suggestion"
          v-model="suggestion"
          rows="3"
          :maxlength="REJECTION_TEXT_MAX_LENGTH"
          placeholder="Another venue or arrangement. This is only a suggestion: nothing is held."
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">
          {{ suggestion.length }} / {{ REJECTION_TEXT_MAX_LENGTH }}
        </p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton
            type="button"
            variant="primary"
            aria-label="Reject booking request"
            :disabled="!canConfirm"
            @click="confirm"
          >
            Reject request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
