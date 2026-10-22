<script setup>
import { SECTION_TONES } from "@/components/common/sectionTone";

// A dashboard section heading on a Bauhaus colour block (black border, hard
// shadow), so sections read as distinct at a glance. Pages pick the colour
// with `sectionTone(index)`. Red and blue take white text, yellow black.
// Used by the organiser and coordinator dashboards.
defineProps({
  id: { type: String, required: true },
  tone: {
    type: String,
    required: true,
    validator: (value) => SECTION_TONES.includes(value),
  },
});

const toneClasses = {
  red: "bg-bauhaus-red text-canvas",
  blue: "bg-bauhaus-blue text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
};
</script>

<template>
  <h2
    :id="id"
    :data-tone="tone"
    class="inline-block border-2 border-ink px-3 py-1 text-2xl font-bold leading-tight shadow-hard sm:border-4 sm:text-3xl"
    :class="toneClasses[tone]"
  >
    <slot />
  </h2>
</template>
