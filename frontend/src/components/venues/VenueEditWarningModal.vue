<script setup>
import BauhausButton from "@/components/common/BauhausButton.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  warnings: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(["confirm", "cancel"]);

// CR-94: Unsuitable (capacity or a required facility) vs warning-only.
// Static class names: Tailwind's scanner can't see built strings.
const OUTCOMES = {
  unsuitable: { label: "Unsuitable", badge: "bg-bauhaus-red text-canvas", card: "bg-bauhaus-red/10" },
  warning: { label: "Warning", badge: "bg-bauhaus-yellow text-ink", card: "bg-bauhaus-yellow/30" },
};
const outcomeOf = (warning) => OUTCOMES[warning.outcome] || OUTCOMES.warning;
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
        aria-labelledby="venue-edit-warning-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="venue-edit-warning-title" class="text-2xl font-black uppercase leading-tight tracking-tight">
          This change may affect upcoming bookings
        </h2>
        <p class="mt-4 text-base font-medium">
          Saving will not change or cancel any booking — resolving this is up to you and the event's coordinator.
          Events affected:
        </p>
        <ul class="mt-4 flex flex-col gap-3">
          <li
            v-for="warning in props.warnings"
            :key="warning.booking_id"
            data-testid="affected-booking"
            :class="['border-2 border-ink p-3', outcomeOf(warning).card]"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <p class="text-sm font-bold uppercase tracking-wide">{{ warning.event_name || `Event ${warning.event_id.slice(0, 8)}` }}</p>
              <span
                data-testid="outcome-badge"
                :class="['border-2 border-ink px-2 py-0.5 text-xs font-black uppercase tracking-widest', outcomeOf(warning).badge]"
              >
                {{ outcomeOf(warning).label }}
              </span>
            </div>
            <ul class="mt-1 list-inside list-disc text-sm font-medium">
              <li v-for="(reason, index) in warning.reasons" :key="index">{{ reason }}</li>
            </ul>
          </li>
        </ul>
        <p
          v-if="props.error"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ props.error }}
        </p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Keep editing" @click="emit('cancel')">
            Keep editing
          </BauhausButton>
          <BauhausButton
            type="button"
            variant="primary"
            aria-label="Save anyway"
            :disabled="props.busy"
            @click="emit('confirm')"
          >
            Save anyway
          </BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
