<script setup>
// Decorative: an organiser's event plan with steps ticked off. Still, the
// first three are done; animated, it ticks them off one by one and starts
// over, unless the visitor prefers reduced motion.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { useMediaQuery } from "@/composables/useMediaQuery";

const props = defineProps({
  animated: { type: Boolean, default: false },
});

const items = ["Idea pitched", "Venue booked", "Gear sorted", "Safety check", "Doors open"];
const STILL_DONE = 3;
const STEP_MS = 900;

const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)", true);
const step = ref(STILL_DONE);
// One extra step past the last item holds the finished plan before it resets.
const doneCount = computed(() => Math.min(step.value, items.length));
let timer = null;

onMounted(() => {
  if (!props.animated || reduceMotion.value) return;
  step.value = 0;
  timer = setInterval(() => {
    step.value = (step.value + 1) % (items.length + 2);
  }, STEP_MS);
});
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="w-64 -rotate-2 border-4 border-ink bg-canvas shadow-hard-lg">
    <p class="border-b-4 border-ink bg-bauhaus-blue px-4 py-3 text-sm font-bold text-canvas">Event plan</p>
    <ul class="flex flex-col gap-3 p-4">
      <li v-for="(item, index) in items" :key="item" :data-done="index < doneCount" class="flex items-center gap-3 text-sm font-bold">
        <span
          class="flex h-5 w-5 shrink-0 items-center justify-center border-2 border-ink text-xs transition-colors"
          :class="index < doneCount ? 'bg-ink text-canvas' : 'bg-canvas'"
        >{{ index < doneCount ? "✓" : "" }}</span>
        <span :class="index < doneCount ? 'text-ink/60 line-through' : ''">{{ item }}</span>
      </li>
    </ul>
  </div>
</template>
