<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import {
  BLOCK_CHANGE_ACTIONS,
  BLOCK_CHANGE_NOTE_MAX_LENGTH,
  blockActions,
  blockSetBy,
  emptyBlockChange,
  toBlockChangePayload,
  validateBlockChange,
} from "@/features/venues/blockChange";
import { blockReasonLabel, formatEventReference } from "@/features/venues/dashboard";
import { bookingStatusLabel, countBookings, formatVenuePeriod } from "@/features/venues/venueProfile";

// SCRUM-54: end a block now, shorten it, or remove one that hasn't started,
// in two steps. The form offers only the changes the block allows (AC2); once
// saved, the parent passes `result` and the modal lists the bookings the block
// no longer covers, each linking to its booking page, where venue staff
// restore it (AC5, AC6). The API enforces every rule shown here.
const props = defineProps({
  open: { type: Boolean, default: false },
  venueName: { type: String, required: true },
  block: { type: Object, default: null },
  result: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
  // Injectable so which changes a block allows can be tested at a fixed time.
  now: { type: Date, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const ACTION_DETAILS = {
  end_now: "The venue is available from now.",
  shorten: "Choose an earlier end. The venue is available from then.",
  remove: "The block hasn't started, so it won't apply at all.",
};

const at = () => props.now ?? new Date();
const allowed = computed(() => blockActions(props.block, at()));
const form = ref(emptyBlockChange());
const attempted = ref(false);
const errors = computed(() => (attempted.value ? validateBlockChange(form.value, props.block, at()) : {}));

const restorableNotice = computed(() => {
  const count = props.result.restorable.length;
  return {
    heading: `${countBookings(count)} can be restored`,
    detail: count === 1
      ? "The venue is free again for the whole of this booking. It stays Affected until you restore it: open it to restore it."
      : "The venue is free again for the whole of each booking below. They stay Affected until you restore them: open one to restore it.",
  };
});
const resultTitle = computed(() => (props.result?.block?.status === "removed" ? "Block removed" : "Block ended early"));

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      form.value = emptyBlockChange(allowed.value[0] ?? "");
      attempted.value = false;
    }
  },
  { immediate: true },
);

function submit() {
  attempted.value = true;
  if (props.busy || Object.keys(validateBlockChange(form.value, props.block, at())).length) return;
  emit("confirm", toBlockChangePayload(form.value));
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
        aria-labelledby="change-block-title"
        class="my-auto w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <template v-if="props.result">
          <h2 id="change-block-title" class="text-2xl font-bold leading-tight">{{ resultTitle }}</h2>
          <p v-if="props.result.block?.status === 'removed'" class="mt-4 text-base font-medium">
            The block on "{{ props.venueName }}" was removed. That time is available again.
          </p>
          <p v-else-if="props.result.block?.period" class="mt-4 text-base font-medium">
            "{{ props.venueName }}" is now blocked {{ formatVenuePeriod(props.result.block.period) }} (Singapore time).
            The rest of the original period is available again.
          </p>
          <div v-if="props.result.restorable.length" class="mt-6 border-4 border-ink bg-bauhaus-yellow p-4">
            <p class="text-sm font-bold">{{ restorableNotice.heading }}</p>
            <p class="mt-1 text-sm font-medium">{{ restorableNotice.detail }}</p>
            <ul class="mt-3 space-y-2" data-testid="block-restorable">
              <li v-for="booking in props.result.restorable" :key="booking.booking_id">
                <RouterLink
                  :to="{ name: 'booking-request', params: { id: booking.booking_id } }"
                  class="block border-2 border-ink bg-canvas px-3 py-2 text-sm hover:bg-muted active-press"
                >
                  <span class="block font-bold">{{ formatEventReference(booking) }}</span>
                  <span class="block font-medium">{{ formatVenuePeriod(booking.period) }}</span>
                  <span class="block text-xs font-bold text-ink/70">
                    {{ bookingStatusLabel(booking.status) }} · Affected: {{ booking.block_reason }}
                  </span>
                  <span v-if="booking.has_pending_replacement" class="mt-1 block text-xs font-bold text-bauhaus-red">
                    Replacement requested: restoring this booking cancels it.
                  </span>
                </RouterLink>
              </li>
            </ul>
          </div>
          <p v-else class="mt-6 text-sm font-bold">No bookings are waiting to be restored.</p>
          <div class="mt-8 flex justify-end">
            <BauhausButton type="button" variant="primary" aria-label="Done" @click="emit('cancel')">Done</BauhausButton>
          </div>
        </template>

        <template v-else-if="props.block">
          <h2 id="change-block-title" class="text-2xl font-bold leading-tight">Change block</h2>
          <div class="mt-4 border-2 border-ink px-3 py-2 text-sm">
            <p class="font-bold">{{ formatVenuePeriod(props.block.period) }}</p>
            <p class="mt-1 font-medium">
              {{ [blockReasonLabel(props.block.reason), props.block.notes].filter(Boolean).join(" · ") }}
            </p>
            <p class="mt-1 text-xs font-medium text-ink/70">{{ blockSetBy(props.block) }}</p>
          </div>

          <fieldset class="mt-6">
            <legend class="text-sm font-bold">What do you want to do?</legend>
            <label
              v-for="action in allowed"
              :key="action"
              class="mt-2 flex cursor-pointer items-start gap-3 border-2 border-ink px-3 py-2 hover:bg-muted"
            >
              <input v-model="form.action" type="radio" name="block-change-action" :value="action" class="mt-1" />
              <span>
                <span class="block text-sm font-bold">{{ BLOCK_CHANGE_ACTIONS[action] }}</span>
                <span class="block text-xs font-medium text-ink/70">{{ ACTION_DETAILS[action] }}</span>
              </span>
            </label>
            <p v-if="errors.action" class="mt-1 text-xs font-bold text-bauhaus-red">{{ errors.action }}</p>
          </fieldset>

          <div v-if="form.action === 'shorten'" class="mt-4">
            <BauhausInput
              v-model="form.endsAt"
              type="datetime-local"
              label="New end (Singapore time)"
              aria-label="New end"
              required
              :error="errors.endsAt"
            />
          </div>

          <label for="block-change-note" class="mt-4 block text-xs font-bold text-ink/70">Note (optional)</label>
          <textarea
            id="block-change-note"
            v-model="form.note"
            rows="3"
            :maxlength="BLOCK_CHANGE_NOTE_MAX_LENGTH"
            :aria-invalid="Boolean(errors.note)"
            class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
          ></textarea>
          <div class="mt-1 flex justify-between gap-3 text-xs font-bold">
            <span class="text-bauhaus-red">{{ errors.note }}</span>
            <span class="text-ink/70">{{ form.note.length }} / {{ BLOCK_CHANGE_NOTE_MAX_LENGTH }}</span>
          </div>

          <p class="mt-4 text-sm font-medium">
            Bookings this block marked Affected stay Affected until venue staff restore them.
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
            <BauhausButton type="button" variant="primary" aria-label="Save change" :disabled="props.busy" @click="submit">
              Save change
            </BauhausButton>
          </div>
        </template>
      </section>
    </div>
  </Teleport>
</template>
