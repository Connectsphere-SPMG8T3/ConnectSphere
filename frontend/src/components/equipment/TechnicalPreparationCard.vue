<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  PREPARATION_LOCKED_MESSAGE,
  PREPARATION_STAGE_OPTIONS,
} from "@/features/equipment/preparation";
import { formatTechnicalTime, notesError, TECHNICAL_NOTES_MAX_LENGTH } from "@/features/equipment/technical";

// CR-110: Technical Support record the event's preparation stage and an
// internal note (AC2). Locked until the Safety Officer has confirmed the event
// (AC1); the parent runs the save and reloads.
const props = defineProps({
  // `{ stage, note, updated_at, updated_by_name }`; missing reads as Not started.
  preparation: { type: Object, default: null },
  // True while the event is Confirmed or in Preparation.
  open: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
  // Another action on the page is running.
  locked: { type: Boolean, default: false },
  error: { type: String, default: null },
});
const emit = defineEmits(["save"]);

const savedStage = computed(() => props.preparation?.stage ?? "not_started");
const savedNote = computed(() => props.preparation?.note ?? "");
const stage = ref(savedStage.value);
const note = ref(savedNote.value);
watch(savedStage, (value) => { stage.value = value; });
watch(savedNote, (value) => { note.value = value; });

const disabled = computed(() => !props.open || props.busy || props.locked);
const shownNoteError = computed(() => notesError(note.value));
const changed = computed(() => stage.value !== savedStage.value || note.value.trim() !== savedNote.value);

function save() {
  if (disabled.value || !changed.value || shownNoteError.value) return;
  emit("save", { stage: stage.value, note: note.value });
}
</script>

<template>
  <BauhausCard background="white" accent="none" data-testid="technical-preparation">
    <h2 class="text-2xl font-bold">Technical preparation</h2>
    <p v-if="!open" class="mt-3 text-sm font-bold">{{ PREPARATION_LOCKED_MESSAGE }}</p>
    <form class="mt-4 flex flex-col gap-4" novalidate @submit.prevent="save">
      <BauhausSelect
        v-model="stage"
        label="Stage"
        :options="PREPARATION_STAGE_OPTIONS"
        :show-placeholder="false"
        compact
        :disabled="disabled"
      />
      <div class="flex flex-col gap-2">
        <label for="technical-preparation-note" class="text-xs font-bold">Preparation notes (internal)</label>
        <textarea
          id="technical-preparation-note"
          v-model="note"
          rows="3"
          :maxlength="TECHNICAL_NOTES_MAX_LENGTH"
          class="w-full border-2 border-ink bg-canvas p-3 text-sm"
          :aria-invalid="shownNoteError ? 'true' : undefined"
          :aria-describedby="shownNoteError ? 'technical-preparation-note-error' : undefined"
          :disabled="disabled"
        />
        <p v-if="shownNoteError" id="technical-preparation-note-error" class="text-sm font-bold text-bauhaus-red">{{ shownNoteError }}</p>
        <p class="text-xs font-bold text-ink/60">The organiser sees the stage, never these notes.</p>
      </div>
      <div v-if="open">
        <BauhausButton type="submit" :disabled="disabled || !changed || !!shownNoteError">
          {{ busy ? "Saving…" : "Save preparation" }}
        </BauhausButton>
      </div>
    </form>
    <p v-if="preparation?.updated_at" class="mt-3 text-xs font-bold text-ink/60">
      Last updated by {{ preparation.updated_by_name ?? "a former staff member" }} · {{ formatTechnicalTime(preparation.updated_at) }}
    </p>
    <p v-if="error" role="alert" class="mt-3 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">{{ error }}</p>
  </BauhausCard>
</template>
