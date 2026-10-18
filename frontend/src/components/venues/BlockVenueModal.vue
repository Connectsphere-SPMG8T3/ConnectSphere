<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  BLOCK_DETAIL_MAX_LENGTH,
  BLOCK_REASONS,
  emptyBlockForm,
  toBlockPayload,
  validateBlockForm,
} from "@/features/venues/blockForm";
import { formatEventReference } from "@/features/venues/dashboard";
import { bookingStatusLabel, formatVenuePeriod } from "@/features/venues/venueProfile";

// SCRUM-51: block a venue in up to three steps. The first submit is a
// preview; if the block overlaps held or approved bookings the parent passes
// them back as `affected` and staff confirm with "Block anyway" (CAL-R1).
// Once saved, the parent passes `result` and the modal lists the bookings
// recorded against the block (AC6). The API enforces every rule shown here.
const props = defineProps({
  open: { type: Boolean, default: false },
  venueName: { type: String, required: true },
  affected: { type: Array, default: () => [] },
  result: { type: Object, default: null },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

const form = ref(emptyBlockForm());
const attempted = ref(false);
const errors = computed(() => (attempted.value ? validateBlockForm(form.value) : {}));
const needsDetail = computed(() => form.value.reason === "other");
const previewing = computed(() => props.affected.length > 0);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      form.value = emptyBlockForm();
      attempted.value = false;
    }
  },
);

function submit(confirm) {
  attempted.value = true;
  if (props.busy || Object.keys(validateBlockForm(form.value)).length) return;
  emit("confirm", toBlockPayload(form.value, { confirm }));
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
        aria-labelledby="block-modal-title"
        class="my-auto w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <template v-if="props.result">
          <h2 id="block-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">
            Venue blocked
          </h2>
          <p v-if="props.result.block?.period" class="mt-4 text-base font-medium">
            "{{ props.venueName }}" is unavailable {{ formatVenuePeriod(props.result.block.period) }} (Singapore time).
          </p>
          <div v-if="props.result.affected.length" class="mt-6 border-4 border-ink bg-bauhaus-yellow p-4">
            <p class="text-sm font-bold">
              Affected bookings. Each is flagged and its coordinator notified; none was cancelled.
            </p>
            <ul class="mt-3 space-y-2" data-testid="block-affected">
              <li
                v-for="booking in props.result.affected"
                :key="booking.booking_id"
                class="border-2 border-ink bg-canvas px-3 py-2 text-sm"
              >
                <span class="block font-bold">{{ formatEventReference(booking) }}</span>
                <span class="block font-medium">{{ formatVenuePeriod(booking.period) }}</span>
                <span class="block text-xs font-bold uppercase tracking-widest text-ink/70">
                  {{ bookingStatusLabel(booking.status) }} · {{ booking.block_reason }}
                </span>
              </li>
            </ul>
          </div>
          <p v-else class="mt-6 text-sm font-bold">No bookings were affected.</p>
          <div class="mt-8 flex justify-end">
            <BauhausButton type="button" variant="primary" aria-label="Done" @click="emit('cancel')">Done</BauhausButton>
          </div>
        </template>

        <template v-else>
          <h2 id="block-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">
            Block venue
          </h2>
          <p class="mt-4 text-base font-medium">
            "{{ props.venueName }}" won't appear in search or take booking requests for an overlapping time. It
            becomes available again when the block ends.
          </p>

          <div class="mt-6 grid gap-4 sm:grid-cols-2">
            <BauhausInput
              v-model="form.startsAt"
              type="datetime-local"
              label="Start (Singapore time)"
              aria-label="Block start"
              required
              :error="errors.startsAt"
            />
            <BauhausInput
              v-model="form.endsAt"
              type="datetime-local"
              label="End (Singapore time)"
              aria-label="Block end"
              required
              :error="errors.endsAt"
            />
          </div>
          <div class="mt-4">
            <BauhausSelect
              v-model="form.reason"
              label="Reason (required)"
              :options="BLOCK_REASONS"
              placeholder="Choose a reason"
              required
              :error="errors.reason"
            />
          </div>
          <label for="block-detail" class="mt-4 block text-xs font-bold uppercase tracking-widest text-ink/70">
            Detail {{ needsDetail ? "(required)" : "(optional)" }}
          </label>
          <textarea
            id="block-detail"
            v-model="form.detail"
            rows="3"
            :maxlength="BLOCK_DETAIL_MAX_LENGTH"
            :aria-invalid="Boolean(errors.detail)"
            class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
          ></textarea>
          <div class="mt-1 flex justify-between gap-3 text-xs font-bold">
            <span class="uppercase tracking-wide text-bauhaus-red">{{ errors.detail }}</span>
            <span class="text-ink/70">{{ form.detail.length }} / {{ BLOCK_DETAIL_MAX_LENGTH }}</span>
          </div>

          <div v-if="previewing" class="mt-6 border-4 border-ink bg-bauhaus-yellow p-4">
            <p class="text-sm font-bold">
              These bookings will be flagged Affected and their coordinators notified. They are not cancelled.
            </p>
            <ul class="mt-3 space-y-2">
              <li
                v-for="booking in props.affected"
                :key="booking.booking_id"
                class="border-2 border-ink bg-canvas px-3 py-2 text-sm"
              >
                <span class="block font-bold">{{ formatEventReference(booking) }}</span>
                <span class="block font-medium">{{ formatVenuePeriod(booking.period) }}</span>
                <span class="block text-xs font-bold uppercase tracking-widest text-ink/70">
                  {{ bookingStatusLabel(booking.status) }}
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
              aria-label="Block anyway"
              :disabled="props.busy"
              @click="submit(true)"
            >
              Block anyway
            </BauhausButton>
            <BauhausButton
              v-else
              type="button"
              variant="primary"
              aria-label="Block venue"
              :disabled="props.busy"
              @click="submit(false)"
            >
              Block venue
            </BauhausButton>
          </div>
        </template>
      </section>
    </div>
  </Teleport>
</template>
