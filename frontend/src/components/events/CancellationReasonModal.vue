<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { CANCELLATION_REASON_MAX_LENGTH } from "@/features/events/cancellation";

// Story 115: the coordinator's reason for rejecting a cancellation request or for
// cancelling directly. Same shape as RejectEventModal; the wording comes from the caller.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  message: { type: String, required: true },
  confirmLabel: { type: String, required: true },
  confirmAriaLabel: { type: String, required: true },
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
        aria-labelledby="cancellation-reason-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="cancellation-reason-title" class="text-2xl font-bold leading-tight">{{ props.title }}</h2>
        <p class="mt-4 text-base font-medium">{{ props.message }}</p>
        <label for="cancellation-reason" class="mt-6 block text-xs font-bold text-ink/70">Reason (required)</label>
        <textarea
          id="cancellation-reason"
          v-model="reason"
          rows="4"
          :maxlength="CANCELLATION_REASON_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ reason.length }} / {{ CANCELLATION_REASON_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Close" @click="emit('cancel')">Go back</BauhausButton>
          <BauhausButton type="button" variant="primary" :aria-label="props.confirmAriaLabel" :disabled="!canConfirm" @click="confirm">
            {{ props.confirmLabel }}
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
