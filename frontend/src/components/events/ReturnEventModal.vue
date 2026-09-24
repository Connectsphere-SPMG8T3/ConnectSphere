<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import { AMENDMENT_TEXT_MAX_LENGTH, EVENT_FIELD_LABELS } from "@/features/events/amendment";

// SCRUM-33: the coordinator's message and the fields to review. A sibling of
// RejectEventModal; the API is the enforcement point for both rules shown here.
const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const message = ref("");
const flaggedFields = ref([]);
const trimmed = computed(() => message.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      message.value = "";
      flaggedFields.value = [];
    }
  },
);

function confirm() {
  if (!canConfirm.value) return;
  // Keep the form's order, not the order the boxes were ticked in.
  const ordered = EVENT_FIELD_LABELS.map((option) => option.value).filter((value) => flaggedFields.value.includes(value));
  emit("confirm", { message: trimmed.value, flaggedFields: ordered });
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('cancel')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="return-modal-title"
        class="w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="return-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Return for amendment?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" goes back to the organiser to edit and resubmit. Planning waits until they do.
        </p>
        <label for="return-message" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">Message to the organiser (required)</label>
        <textarea
          id="return-message"
          v-model="message"
          rows="4"
          :maxlength="AMENDMENT_TEXT_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ message.length }} / {{ AMENDMENT_TEXT_MAX_LENGTH }}</p>
        <div class="mt-4">
          <BauhausCheckboxGroup v-model="flaggedFields" label="Fields to review (optional)" :options="EVENT_FIELD_LABELS" />
        </div>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Return request" :disabled="!canConfirm" @click="confirm">
            Return request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
