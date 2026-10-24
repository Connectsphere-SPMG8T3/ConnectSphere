<script setup>
// Decorative: an event ticket with its stub. Animated, it rocks gently from
// side to side, unless the visitor prefers reduced motion.
import { onBeforeUnmount, onMounted, ref } from "vue";

import { useMediaQuery } from "@/composables/useMediaQuery";

const props = defineProps({
  animated: { type: Boolean, default: false },
});

const ROCK_MS = 1600;

const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)", true);
const tilted = ref(true);
let timer = null;

onMounted(() => {
  if (!props.animated || reduceMotion.value) return;
  timer = setInterval(() => {
    tilted.value = !tilted.value;
  }, ROCK_MS);
});
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="flex border-4 border-ink bg-canvas shadow-hard-lg transition-transform duration-700" :class="tilted ? 'rotate-3' : '-rotate-1'">
    <div class="flex w-48 flex-col p-5">
      <p class="text-xs font-bold">Admit one</p>
      <p class="mt-3 text-2xl font-bold leading-tight">Your next favourite event</p>
      <p class="mt-5 text-xs font-bold">Somewhere in Singapore</p>
    </div>
    <div class="flex w-20 items-center justify-center border-l-4 border-dashed border-ink bg-bauhaus-red px-2 text-center text-xs font-bold text-canvas">Spot saved</div>
  </div>
</template>
