<script setup>
import { ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { BOOKING_NOTE_MAX_LENGTH } from "@/features/venues/venueBookingStore";

const props = defineProps({
  open: { type: Boolean, default: false },
  venueName: { type: String, required: true },
  eventName: { type: String, required: true },
  period: { type: String, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
  // What is in the way, as describeConflict words it (SCRUM-21 AC2).
  conflict: { type: String, default: "" },
  // CR-95 AC4, AC7: the affected venue this request replaces, and whether
  // requesting it sends the event back to Planning.
  replacesVenueName: { type: String, default: "" },
  returnsToPlanning: { type: Boolean, default: false },
});

const emit = defineEmits(["confirm", "cancel"]);

const note = ref("");

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) note.value = "";
  },
);

function confirm() {
  if (!props.busy) emit("confirm", note.value);
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
        aria-labelledby="request-venue-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="request-venue-title" class="text-2xl font-black uppercase leading-tight tracking-tight">Request this venue?</h2>
        <p class="mt-4 text-base font-medium">
          {{ props.venueName }} will be held for "{{ props.eventName }}" while venue staff decide. Other events can't
          book it for this time in the meantime.
        </p>
        <p class="mt-3 border-2 border-ink bg-surface px-3 py-2 text-sm font-bold">{{ props.period }}</p>
        <p v-if="props.replacesVenueName" class="mt-3 text-sm font-medium" data-testid="replaces-venue">
          This replaces {{ props.replacesVenueName }}, which is no longer available. It stays on the event until your
          replacement is approved.
          <template v-if="props.returnsToPlanning">
            The event goes back to Planning and needs the safety check again.
          </template>
        </p>
        <label for="request-venue-note" class="mt-6 block text-xs font-bold uppercase tracking-widest text-ink/70">
          Note for venue staff (optional)
        </label>
        <textarea
          id="request-venue-note"
          v-model="note"
          rows="3"
          :maxlength="BOOKING_NOTE_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ note.length }} / {{ BOOKING_NOTE_MAX_LENGTH }}</p>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
          <span v-if="props.conflict" class="mt-1 block font-medium">{{ props.conflict }}</span>
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Cancel" @click="emit('cancel')">Cancel</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Request venue" :disabled="props.busy" @click="confirm">
            Request venue
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
