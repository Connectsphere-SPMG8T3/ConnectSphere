<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { AMENDMENT_TEXT_MAX_LENGTH } from "@/features/events/amendment";

// SCRUM-33: the organiser's resubmission note, required by the API (§5 guard).
const props = defineProps({
  open: { type: Boolean, default: false },
  eventName: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const note = ref("");
const trimmed = computed(() => note.value.trim());
const canConfirm = computed(() => trimmed.value.length > 0 && !props.busy);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) note.value = "";
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
        aria-labelledby="resubmit-modal-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="resubmit-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Resubmit this request?</h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.eventName }}" goes back to your coordinator for review. Tell them what you changed.
        </p>
        <label for="resubmit-note" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">What changed (required)</label>
        <textarea
          id="resubmit-note"
          v-model="note"
          rows="4"
          :maxlength="AMENDMENT_TEXT_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ note.length }} / {{ AMENDMENT_TEXT_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Resubmit request" :disabled="!canConfirm" @click="confirm">
            Resubmit request
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
