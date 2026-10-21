<script setup>
import BauhausCard from "./BauhausCard.vue";

// Card appearance, accessibility attributes and click listeners fall through
// to BauhausCard so dashboards keep their existing interaction contracts.
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  detail: { type: String, default: "" },
});
</script>

<template>
  <BauhausCard class="h-full">
    <!-- Minimum space keeps figures aligned; larger text can still grow. -->
    <p class="min-h-8 text-xs font-bold leading-4 opacity-80">{{ label }}</p>
    <p class="mt-2 text-5xl font-bold">{{ value }}</p>
    <p v-if="detail || $slots.detail" class="mt-2 flex min-h-8 items-baseline gap-2 text-xs font-medium leading-4 text-ink/60">
      <slot name="detail">{{ detail }}</slot>
    </p>
  </BauhausCard>
</template>
