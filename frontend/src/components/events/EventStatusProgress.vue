<script setup>
import { computed } from "vue";

import { statusProgress } from "@/features/events/statusProgress";

const props = defineProps({
  status: { type: String, required: true },
});

const progress = computed(() => statusProgress(props.status));

// Full class names so Tailwind's scanner sees them. Done is ink, the current
// step is blue (informational), a returned request is red (it's blocked).
const BAR_CLASSES = {
  done: "bg-ink",
  current: "bg-bauhaus-blue",
  returned: "bg-bauhaus-red",
  upcoming: "bg-canvas",
};
const LABEL_CLASSES = {
  done: "text-ink",
  current: "text-ink font-bold",
  returned: "text-ink font-bold",
  upcoming: "text-ink/50",
};
</script>

<template>
  <ol v-if="progress.steps.length" aria-label="Event progress" class="grid grid-cols-5 gap-1 sm:gap-2">
    <li
      v-for="step in progress.steps"
      :key="step.status"
      :aria-current="step.state === 'current' || step.state === 'returned' ? 'step' : undefined"
    >
      <span data-bar class="block h-3 border-2 border-ink" :class="BAR_CLASSES[step.state]" aria-hidden="true" />
      <span
        class="mt-2 block text-xs font-bold leading-tight sm:text-xs"
        :class="LABEL_CLASSES[step.state]"
      >
        {{ step.label }}<span v-if="step.state === 'done'" class="sr-only"> (done)</span>
      </span>
    </li>
  </ol>
  <p
    v-else
    data-testid="status-outcome"
    class="inline-block border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold shadow-hard"
  >
    {{ progress.label }}
  </p>
</template>
