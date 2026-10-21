<script setup>
/**
 * What a coordinator sees on a venue booking flagged Affected (CR-95 AC3,
 * AC4): the alert, why, and either the way to ask for a replacement or the
 * replacement already asked for. The event page decides which booking and
 * whether a replacement can still be requested; this only draws them.
 */
import BauhausButton from "@/components/common/BauhausButton.vue";
import { BOOKING_STATUS_LABELS } from "@/features/venues/bookingRequest";

defineProps({
  reason: { type: String, default: "" },
  replacement: { type: Object, default: null },
  canReplace: { type: Boolean, default: false },
});

const emit = defineEmits(["replace"]);
</script>

<template>
  <div class="mt-3 border-l-4 border-bauhaus-red pl-3" data-testid="venue-affected">
    <p class="inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-bold text-canvas">
      Needs alternative venue
    </p>
    <p v-if="reason" class="mt-2 text-sm font-medium">{{ reason }}</p>
    <div v-if="replacement" class="mt-3" data-testid="venue-replacement">
      <p class="text-xs font-bold text-ink/70">Replacement requested</p>
      <p class="mt-1 text-sm font-bold">
        {{ replacement.venue_name ?? "Venue" }}
        <span class="ml-2 border-2 border-ink bg-bauhaus-yellow px-2 py-0.5 text-xs font-bold">
          {{ BOOKING_STATUS_LABELS[replacement.status] ?? replacement.status }}
        </span>
      </p>
    </div>
    <BauhausButton v-else-if="canReplace" class="mt-3" variant="secondary" @click="emit('replace')">
      Find replacement
    </BauhausButton>
  </div>
</template>
