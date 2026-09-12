<script setup>
import { computed } from "vue";

const props = defineProps({
  background: {
    type: String,
    default: "white",
    validator: (value) => ["white", "red", "blue", "yellow"].includes(value),
  },
  accent: {
    type: String,
    default: "circle",
    validator: (value) => ["circle", "square", "triangle", "none"].includes(value),
  },
  accentColor: {
    type: String,
    default: "bauhaus-yellow",
  },
});

const backgroundClasses = {
  white: "bg-canvas text-ink",
  red: "bg-bauhaus-red text-canvas",
  blue: "bg-bauhaus-blue text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
};

// Tailwind's scanner needs full, static class names to keep them in the
// build — dynamic template interpolation (e.g. `bg-${accentColor}`) is
// invisible to it, so every accent colour variant is spelled out here.
const accentBgClasses = {
  "bauhaus-red": "bg-bauhaus-red",
  "bauhaus-blue": "bg-bauhaus-blue",
  "bauhaus-yellow": "bg-bauhaus-yellow",
  ink: "bg-ink",
  canvas: "bg-canvas",
};

const accentBorderClasses = {
  "bauhaus-red": "border-l-bauhaus-red",
  "bauhaus-blue": "border-l-bauhaus-blue",
  "bauhaus-yellow": "border-l-bauhaus-yellow",
  ink: "border-l-ink",
  canvas: "border-l-canvas",
};

const classes = computed(() => backgroundClasses[props.background]);
const accentBgClass = computed(() => accentBgClasses[props.accentColor] ?? accentBgClasses["bauhaus-yellow"]);
const accentBorderClass = computed(
  () => accentBorderClasses[props.accentColor] ?? accentBorderClasses["bauhaus-yellow"],
);
</script>

<template>
  <div class="relative overflow-hidden border-2 border-ink p-6 shadow-hard-lg sm:border-4 sm:p-8" :class="classes">
    <span
      v-if="accent === 'circle'"
      class="absolute -right-6 -top-6 h-16 w-16 rounded-full sm:h-20 sm:w-20"
      :class="accentBgClass"
      aria-hidden="true"
    />
    <span
      v-else-if="accent === 'square'"
      class="absolute -right-4 -top-4 h-14 w-14 border-2 border-ink sm:h-16 sm:w-16 sm:border-4"
      :class="accentBgClass"
      aria-hidden="true"
    />
    <span
      v-else-if="accent === 'triangle'"
      class="absolute -right-2 -top-2 h-0 w-0 border-b-[56px] border-l-[56px] border-b-transparent sm:border-b-[72px] sm:border-l-[72px]"
      :class="accentBorderClass"
      aria-hidden="true"
    />
    <div class="relative z-10">
      <slot />
    </div>
  </div>
</template>
