<script setup>
import { computed } from "vue";

import { suitabilityBadge } from "@/features/venues/suitability";

const props = defineProps({
  suitability: { type: Object, default: null },
});

const badge = computed(() => suitabilityBadge(props.suitability));
</script>

<template>
  <span
    v-if="badge"
    data-testid="suitability-badge"
    class="border-2 border-ink px-3 py-1 text-xs font-bold"
    :class="badge.classes"
  >
    {{ badge.text }}
  </span>
</template>
