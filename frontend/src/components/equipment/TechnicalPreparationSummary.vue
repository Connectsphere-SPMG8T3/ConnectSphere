<script setup>
import { preparationStageLabel } from "@/features/equipment/preparation";
import { formatTechnicalTime } from "@/features/equipment/technical";

// CR-110 AC4: the assigned coordinator's read-only view of technical
// preparation, with the internal note. Organisers never get this component.
defineProps({
  // `{ stage, note, updated_at, updated_by_name }`
  preparation: { type: Object, required: true },
});
</script>

<template>
  <section data-testid="technical-preparation-summary" aria-labelledby="technical-preparation-summary-title">
    <h3 id="technical-preparation-summary-title" class="text-lg font-bold">Technical preparation</h3>
    <p class="mt-2 font-medium">{{ preparationStageLabel(preparation.stage) }}</p>
    <p v-if="preparation.note" class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{{ preparation.note }}</p>
    <p v-if="preparation.updated_at" class="mt-2 text-xs font-bold text-ink/60">
      {{ preparation.updated_by_name ?? "A former staff member" }} · {{ formatTechnicalTime(preparation.updated_at) }}
    </p>
  </section>
</template>
