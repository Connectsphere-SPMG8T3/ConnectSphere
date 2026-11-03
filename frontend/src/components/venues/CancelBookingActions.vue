<script setup>
/**
 * The Cancel buttons under a venue panel on the coordinator's event page
 * (SCRUM-85): one for the booking, and one for a pending replacement beside it.
 * The page asks for confirmation and calls the API; this only offers the choice.
 */
import BauhausButton from "@/components/common/BauhausButton.vue";

defineProps({
  // `[{ booking, label }]` from `cancellableBookings`.
  items: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["cancel"]);
</script>

<template>
  <div v-if="items.length" class="mt-4 flex flex-wrap gap-3" data-testid="cancel-booking-actions">
    <BauhausButton
      v-for="item in items"
      :key="item.booking.id"
      variant="outline"
      :aria-label="`${item.label}: ${item.booking.venue_name ?? 'venue'}`"
      :disabled="busy"
      @click="emit('cancel', item.booking)"
    >
      {{ item.label }}
    </BauhausButton>
  </div>
</template>
