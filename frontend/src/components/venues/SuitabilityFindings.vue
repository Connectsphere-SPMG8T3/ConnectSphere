<script setup>
import { reasonLabel } from "@/features/venues/suitability";

defineProps({
  suitability: { type: Object, default: null },
});
</script>

<template>
  <ul v-if="suitability?.reasons?.length" class="flex flex-col gap-1" data-testid="suitability-findings">
    <li
      v-for="reason in suitability.reasons"
      :key="reason.code + reason.message"
      class="flex items-start gap-2 text-sm font-bold"
      :class="reason.severity === 'unsuitable' ? 'text-bauhaus-red' : 'text-ink'"
    >
      <span class="mt-1.5 inline-block h-2 w-2 shrink-0 bg-current" aria-hidden="true" />
      <span>
        <span class="text-xs uppercase tracking-widest">{{ reasonLabel(reason) }}:</span>
        {{ reason.message }}
      </span>
    </li>
  </ul>
</template>
