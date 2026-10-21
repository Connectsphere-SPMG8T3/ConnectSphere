<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { REJECT_REASON_MAX_LENGTH } from "@/features/events/eventReviewStore";

const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const reason = ref("");
const trimmed = computed(() => reason.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) reason.value = "";
  },
);

function confirm() {
  if (canConfirm.value) emit("confirm", trimmed.value);
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
        aria-labelledby="reject-modal-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="reject-modal-title" class="text-2xl font-bold leading-tight">Reject this request?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" will be closed and can't be resubmitted. The organiser will see your reason.
        </p>
        <label for="reject-reason" class="mt-6 block text-xs font-bold text-ink/70">Reason (required)</label>
        <textarea
          id="reject-reason"
          v-model="reason"
          rows="4"
          :maxlength="REJECT_REASON_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ reason.length }} / {{ REJECT_REASON_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Reject request" :disabled="!canConfirm" @click="confirm">
            Reject request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
