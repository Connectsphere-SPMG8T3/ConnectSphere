<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { REQUEST_STATUS_LABELS } from "@/features/equipment/equipmentRequest";
import {
  canMarkNotAvailable,
  canReserve,
  NOT_AVAILABLE_REASON_MAX_LENGTH,
  notesError,
  reasonError,
  TECHNICAL_NOTES_MAX_LENGTH,
} from "@/features/equipment/technical";

// SCRUM-24: one request line as Technical Support arrange it. Reserve (AC1),
// mark Not available with a reason (AC3, AC9) and keep internal notes (AC9).
// The parent runs the actions; this only collects input and shows the result.
const props = defineProps({
  line: { type: Object, required: true },
  // False once the event has left planning, safety review and confirmed.
  open: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  // Another line's action is running.
  locked: { type: Boolean, default: false },
  error: { type: String, default: null },
});
const emit = defineEmits(["reserve", "not-available", "save-note"]);

// Static class names: Tailwind can't see built ones.
const STATUS_BADGE_CLASSES = {
  pending: "bg-bauhaus-yellow text-ink",
  reserved: "bg-bauhaus-blue text-canvas",
  rejected: "bg-bauhaus-red text-canvas",
  re_review: "bg-bauhaus-yellow text-ink",
  released: "bg-canvas text-ink",
};

const askingReason = ref(false);
const reason = ref("");
const reasonTouched = ref(false);
const notes = ref(props.line.technical_notes ?? "");

watch(() => props.line.technical_notes, (value) => { notes.value = value ?? ""; });
watch(() => props.line.status, () => {
  askingReason.value = false;
  reason.value = "";
  reasonTouched.value = false;
});

const disabled = computed(() => props.busy || props.locked);
const shownReasonError = computed(() => (reasonTouched.value ? reasonError(reason.value) : null));
const shownNotesError = computed(() => notesError(notes.value));
const notesChanged = computed(() => notes.value.trim() !== (props.line.technical_notes ?? ""));
const ids = computed(() => ({
  reason: `line-${props.line.id}-reason`,
  reasonError: `line-${props.line.id}-reason-error`,
  notes: `line-${props.line.id}-notes`,
  notesError: `line-${props.line.id}-notes-error`,
}));

function submitReason() {
  reasonTouched.value = true;
  if (reasonError(reason.value)) return;
  emit("not-available", reason.value);
}

function saveNote() {
  if (shownNotesError.value || !notesChanged.value) return;
  emit("save-note", notes.value);
}
</script>

<template>
  <article class="flex min-w-0 flex-col gap-3 border-2 border-ink bg-canvas p-4 shadow-hard sm:border-4" :aria-busy="busy">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h3 class="text-lg font-black uppercase leading-tight tracking-tighter">
        {{ line.equipment_name }} <span class="font-bold">× {{ line.quantity }}</span>
      </h3>
      <span class="shrink-0 border-2 border-ink px-3 py-1 text-[10px] font-bold uppercase tracking-widest" :class="STATUS_BADGE_CLASSES[line.status]">
        {{ REQUEST_STATUS_LABELS[line.status] ?? line.status }}
      </span>
    </div>
    <p v-if="line.technical_requirements" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm font-medium">
      <span class="font-bold">Requirements:</span> {{ line.technical_requirements }}
    </p>
    <p v-if="line.status === 're_review'" class="border-l-4 border-bauhaus-yellow pl-2 text-sm font-bold">
      The event's time changed and this no longer fits. Its reservation is kept until you reserve it again or mark it not available.
    </p>
    <p v-if="line.not_available_reason" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">
      <span class="font-bold">Not available:</span> {{ line.not_available_reason }}
    </p>
    <p v-if="error" role="alert" class="border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">{{ error }}</p>

    <div v-if="open && (canReserve(line.status) || canMarkNotAvailable(line.status))" class="flex flex-wrap gap-2">
      <BauhausButton v-if="canReserve(line.status)" variant="secondary" :disabled="disabled" @click="emit('reserve')">
        {{ busy ? "Working…" : line.status === "re_review" ? "Reserve again" : "Reserve" }}
      </BauhausButton>
      <BauhausButton
        v-if="canMarkNotAvailable(line.status) && !askingReason"
        variant="outline"
        :disabled="disabled"
        @click="askingReason = true"
      >
        Mark not available
      </BauhausButton>
    </div>

    <form v-if="open && askingReason && canMarkNotAvailable(line.status)" class="flex flex-col gap-2" novalidate @submit.prevent="submitReason">
      <label :for="ids.reason" class="text-xs font-bold uppercase tracking-widest">Why is it not available? *</label>
      <textarea
        :id="ids.reason"
        v-model="reason"
        rows="2"
        :maxlength="NOT_AVAILABLE_REASON_MAX_LENGTH"
        class="w-full border-2 border-ink bg-canvas p-3 text-sm"
        :aria-invalid="shownReasonError ? 'true' : undefined"
        :aria-describedby="shownReasonError ? ids.reasonError : undefined"
        :disabled="disabled"
        @blur="reasonTouched = true"
      />
      <p v-if="shownReasonError" :id="ids.reasonError" class="text-sm font-bold text-bauhaus-red">{{ shownReasonError }}</p>
      <div class="flex flex-wrap gap-2">
        <BauhausButton type="submit" variant="primary" :disabled="disabled">Confirm not available</BauhausButton>
        <BauhausButton variant="outline" :disabled="disabled" @click="askingReason = false; reasonTouched = false">Cancel</BauhausButton>
      </div>
    </form>

    <form v-if="open" class="flex flex-col gap-2 border-t-2 border-ink pt-3" novalidate @submit.prevent="saveNote">
      <label :for="ids.notes" class="text-xs font-bold uppercase tracking-widest">Technical notes (internal)</label>
      <textarea
        :id="ids.notes"
        v-model="notes"
        rows="2"
        :maxlength="TECHNICAL_NOTES_MAX_LENGTH"
        class="w-full border-2 border-ink bg-canvas p-3 text-sm"
        :aria-invalid="shownNotesError ? 'true' : undefined"
        :aria-describedby="shownNotesError ? ids.notesError : undefined"
        :disabled="disabled"
      />
      <p v-if="shownNotesError" :id="ids.notesError" class="text-sm font-bold text-bauhaus-red">{{ shownNotesError }}</p>
      <div>
        <BauhausButton type="submit" variant="outline" :disabled="disabled || !notesChanged || !!shownNotesError">Save notes</BauhausButton>
      </div>
    </form>
    <p v-else-if="line.technical_notes" class="whitespace-pre-wrap [overflow-wrap:anywhere] border-t-2 border-ink pt-3 text-sm">
      <span class="font-bold">Technical notes:</span> {{ line.technical_notes }}
    </p>
  </article>
</template>
