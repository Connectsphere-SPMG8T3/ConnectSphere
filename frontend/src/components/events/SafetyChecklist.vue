<script setup>
// CR-108 AC1-AC2: the six-factor safety checklist. Five factors are marked for each venue booking;
// equipment placement is marked once for the event. v-model is the `marks` object kept by
// features/events/safetyChecklist.js.
import { computed, watch } from "vue";
import BauhausRadioGroup from "@/components/common/BauhausRadioGroup.vue";
import { SAFETY_FACTORS, SAFETY_RATINGS, markKey } from "@/features/events/safetyChecklist";

const props = defineProps({
  // [{ booking_id, venue_name }]
  venues: { type: Array, required: true },
  modelValue: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);

const venueFactors = SAFETY_FACTORS.filter((factor) => factor.scope === "venue");
const eventFactors = SAFETY_FACTORS.filter((factor) => factor.scope === "event");
const sections = computed(() => [
  ...props.venues.map((venue) => ({ key: venue.booking_id, title: venue.venue_name, bookingId: venue.booking_id, factors: venueFactors })),
  { key: "event", title: "Whole event", bookingId: null, factors: eventFactors },
]);

const blank = { rating: null, note: "" };
const mark = (factor, bookingId) => props.modelValue[markKey(factor, bookingId)] ?? blank;

// The prop only catches up on the next render, so two quick changes would each start from the same
// stale marks and the first would be lost. Build on what was last emitted until the prop arrives.
let emitted = null;
watch(() => props.modelValue, () => { emitted = null; });

function change(factor, bookingId, patch) {
  const marks = emitted ?? props.modelValue;
  const key = markKey(factor, bookingId);
  emitted = { ...marks, [key]: { ...(marks[key] ?? blank), ...patch } };
  emit("update:modelValue", emitted);
}

const noteId = (factor, bookingId) => `safety-note-${factor}-${bookingId ?? "event"}`;
</script>

<template>
  <div>
    <section v-for="section in sections" :key="section.key" class="mt-6 border-t-2 border-ink pt-4 first:mt-0 first:border-t-0 first:pt-0">
      <h3 class="text-xl font-bold">{{ section.title }}</h3>
      <div class="mt-2 grid gap-6 md:grid-cols-2">
        <div v-for="factor in section.factors" :key="factor.value" class="min-w-0">
          <BauhausRadioGroup
            :label="factor.label"
            :options="SAFETY_RATINGS"
            :model-value="mark(factor.value, section.bookingId).rating"
            :disabled="disabled"
            required
            @update:model-value="change(factor.value, section.bookingId, { rating: $event })"
          />
          <label :for="noteId(factor.value, section.bookingId)" class="mt-2 block text-sm font-medium">Note (optional)</label>
          <input
            :id="noteId(factor.value, section.bookingId)"
            type="text"
            maxlength="1000"
            :aria-label="`${factor.label} note for ${section.title}`"
            class="mt-1 w-full border-2 border-ink bg-canvas p-2"
            :value="mark(factor.value, section.bookingId).note"
            :disabled="disabled"
            @input="change(factor.value, section.bookingId, { note: $event.target.value })"
          />
        </div>
      </div>
    </section>
  </div>
</template>
