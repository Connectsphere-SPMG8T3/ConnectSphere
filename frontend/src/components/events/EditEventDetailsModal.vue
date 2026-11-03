<script setup>
import { computed, reactive, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import { changedDetails, detailsFormErrors, detailsFormFrom } from "@/features/events/detailsEdit";
import { EVENT_TEXT_LIMITS } from "@/features/events/eventTextRules";

// Story 112: the assigned coordinator's direct edit of the four ordinary fields. Significant
// fields are deliberately absent (AC2); the API refuses them whatever this form sends.
const props = defineProps({
  open: { type: Boolean, default: false },
  event: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
  // The save was refused as a conflict (409): the page is out of date, so offer a reload.
  conflict: { type: Boolean, default: false },
});

const emit = defineEmits(["confirm", "cancel", "reload"]);

const form = reactive(detailsFormFrom(props.event));
const changes = computed(() => changedDetails(props.event, form));
// Like the API, check only what is being changed: an event saved before a field was
// required can still have its other details fixed.
const errors = computed(() =>
  Object.fromEntries(Object.entries(detailsFormErrors(form)).filter(([field]) => field in changes.value)),
);
const canSave = computed(
  () => Object.keys(changes.value).length > 0 && Object.keys(errors.value).length === 0 && !props.busy,
);
const canReload = computed(() => props.conflict && Boolean(props.error));

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) Object.assign(form, detailsFormFrom(props.event));
  },
);

function save() {
  if (!canSave.value) return;
  emit("confirm", changes.value);
}

const areaClass =
  "mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow";
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
        aria-labelledby="edit-details-title"
        class="my-auto w-full max-w-2xl border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="edit-details-title" class="text-2xl font-bold leading-tight">Edit event details</h2>
        <p class="mt-4 text-base font-medium">
          Routine fixes save straight away and don't send anything for re-review. Changes to the date, time,
          attendance, venue or equipment go through a change request.
        </p>
        <div class="mt-6 flex flex-col gap-4">
          <BauhausInput v-model="form.name" label="Event title" required compact :error="errors.name ?? ''" />
          <div>
            <label for="edit-purpose" class="block text-xs font-bold text-ink">Purpose <span aria-hidden="true">*</span></label>
            <textarea id="edit-purpose" v-model="form.purpose" rows="2" :class="areaClass" :aria-invalid="Boolean(errors.purpose)"></textarea>
            <p v-if="errors.purpose" class="mt-1 text-xs font-bold text-bauhaus-red">{{ errors.purpose }}</p>
          </div>
          <div>
            <label for="edit-description" class="block text-xs font-bold text-ink">Description</label>
            <textarea id="edit-description" v-model="form.description" rows="4" :class="areaClass" :aria-invalid="Boolean(errors.description)"></textarea>
            <p v-if="errors.description" class="mt-1 text-xs font-bold text-bauhaus-red">{{ errors.description }}</p>
            <p class="mt-1 text-right text-xs font-bold text-ink/70">{{ form.description.length }} / {{ EVENT_TEXT_LIMITS.descriptionMax }}</p>
          </div>
          <div>
            <label for="edit-accessibility" class="block text-xs font-bold text-ink">Accessibility notes</label>
            <textarea id="edit-accessibility" v-model="form.accessibility_needs" rows="3" :class="areaClass"></textarea>
          </div>
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
          <BauhausButton v-if="canReload" type="button" variant="yellow" aria-label="Reload event" @click="emit('reload')">
            Reload
          </BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Save details" :disabled="!canSave" @click="save">
            Save details
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
