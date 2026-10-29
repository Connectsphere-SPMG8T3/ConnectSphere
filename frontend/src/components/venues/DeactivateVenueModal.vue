<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import { INACTIVE_REASONS, bookingStatusLabel, countBookings, formatVenuePeriod } from "@/features/venues/venueProfile";
import { formatEventReference } from "@/features/venues/dashboard";

// SCRUM-64: deactivate a venue in two steps. The first submit is a preview;
// if the venue has future held or approved bookings the parent passes them
// back as `affected` and staff confirm with "Deactivate anyway". The API is
// the enforcement point for every rule shown here.
const NOTE_MAX_LENGTH = 500;
// A flag survives reactivation, so deactivating again lists bookings that are
// already flagged; the database keeps their flag and does not notify again.
const FLAG_LABELS = { affected: "Affected", conflict: "Conflict", unsuitable: "Unsuitable", safety_rejected: "Safety rejected" };

const props = defineProps({
  open: { type: Boolean, default: false },
  venueName: { type: String, required: true },
  affected: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const reason = ref("");
const note = ref("");
const needsNote = computed(() => reason.value === "other");
const valid = computed(() => reason.value !== "" && (!needsNote.value || note.value.trim().length > 0));
const previewing = computed(() => props.affected.length > 0);
const someAlreadyFlagged = computed(() => props.affected.some((booking) => booking.flag));

// What happens to the listed bookings, in the singular when there is just
// one. Already-flagged bookings keep their flag and are not notified again.
const previewNotice = computed(() => {
  const one = props.affected.length === 1;
  let detail;
  if (one && someAlreadyFlagged.value) {
    detail = "It is already flagged, so it keeps its flag and its coordinator is not told again. It will not be cancelled.";
  } else if (someAlreadyFlagged.value) {
    detail =
      "If you go ahead, any booking not already flagged will be marked Affected and its coordinator told so they can find another venue. Bookings already flagged keep their flag, and their coordinators are not told again. No booking will be cancelled.";
  } else if (one) {
    detail = "If you go ahead, it will be marked Affected and its coordinator told so they can find another venue. It will not be cancelled.";
  } else {
    detail = "If you go ahead, each one will be marked Affected and its coordinator told so they can find another venue. No booking will be cancelled.";
  }
  return { heading: `Deactivating this venue affects ${countBookings(props.affected.length)}`, detail };
});

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      reason.value = "";
      note.value = "";
    }
  },
);

function submit(confirm) {
  if (!valid.value || props.busy) return;
  emit("confirm", { reason: reason.value, note: note.value.trim(), confirm });
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('cancel')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="deactivate-modal-title"
        class="my-auto w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="deactivate-modal-title" class="text-2xl font-bold leading-tight">
          Deactivate venue?
        </h2>
        <p class="mt-4 text-base font-medium">
          "{{ props.venueName }}" stops appearing in venue search and takes no new booking requests. You can reactivate it later.
        </p>

        <div class="mt-6">
          <BauhausSelect
            v-model="reason"
            label="Reason (required)"
            :options="INACTIVE_REASONS"
            placeholder="Choose a reason"
            required
          />
        </div>
        <label for="deactivate-note" class="mt-4 block text-xs font-bold text-ink/70">
          Note {{ needsNote ? "(required)" : "(optional)" }}
        </label>
        <textarea
          id="deactivate-note"
          v-model="note"
          rows="3"
          :maxlength="NOTE_MAX_LENGTH"
          class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
        ></textarea>
        <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ note.length }} / {{ NOTE_MAX_LENGTH }}</p>

        <div v-if="previewing" class="mt-6 border-4 border-ink bg-bauhaus-yellow p-4">
          <p class="text-sm font-bold">{{ previewNotice.heading }}</p>
          <p class="mt-1 text-sm font-medium">{{ previewNotice.detail }}</p>
          <ul class="mt-3 space-y-2">
            <li
              v-for="booking in props.affected"
              :key="booking.booking_id"
              class="border-2 border-ink bg-canvas px-3 py-2 text-sm"
            >
              <span class="block font-bold">{{ formatEventReference(booking) }}</span>
              <span class="block font-medium">{{ formatVenuePeriod(booking.period) }}</span>
              <span class="block text-xs font-bold text-ink/70">
                {{ bookingStatusLabel(booking.status) }}
              </span>
              <span v-if="booking.flag" class="block text-xs font-bold">
                Already flagged: {{ FLAG_LABELS[booking.flag] ?? booking.flag }}
              </span>
            </li>
          </ul>
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
          <BauhausButton
            v-if="previewing"
            type="button"
            variant="primary"
            aria-label="Deactivate anyway"
            :disabled="!valid || props.busy"
            @click="submit(true)"
          >
            Deactivate anyway
          </BauhausButton>
          <BauhausButton
            v-else
            type="button"
            variant="primary"
            aria-label="Deactivate venue"
            :disabled="!valid || props.busy"
            @click="submit(false)"
          >
            Deactivate venue
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
