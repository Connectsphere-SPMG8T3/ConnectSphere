<script setup>
import { computed } from "vue";

const props = defineProps({
  clickable: {
    type: Boolean,
    default: false,
  },
  /**
   * The card's tone. It colours a rule down the card's leading edge rather than
   * filling the whole surface, so colour stays free to mean something (red for
   * blocked, yellow for needs attention, blue for informational).
   */
  background: {
    type: String,
    default: "white",
    validator: (value) => ["white", "red", "blue", "yellow", "green"].includes(value),
  },
  /** Greys the card out (grey fill, faded text, grey stripe), for a closed item such as a rejected request. */
  dimmed: { type: Boolean, default: false },
  accent: {
    type: String,
    default: "circle",
    validator: (value) => ["circle", "square", "triangle", "none"].includes(value),
  },
  accentColor: {
    type: String,
    default: "bauhaus-yellow",
  },
  compact: {
    type: Boolean,
    default: false,
  },
  allowOverflow: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["click"]);

// Enter activates the card only when pressed on the card itself (`.self` in the
// template). An Enter bubbling up from a field inside the card must reach the
// browser, which submits the form or starts a new line in a textarea.
function activate() {
  if (props.clickable) emit("click");
}

// Tailwind's scanner needs full, static class names to keep them in the
// build — dynamic template interpolation (e.g. `bg-${accentColor}`) is
// invisible to it, so every colour variant is spelled out here.
const toneClasses = {
  white: "",
  red: "bg-bauhaus-red",
  blue: "bg-bauhaus-blue",
  yellow: "bg-bauhaus-yellow",
  green: "bg-bauhaus-green",
};

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

const toneClass = computed(() => (props.dimmed ? "bg-ink/30" : toneClasses[props.background] ?? ""));
const accentBgClass = computed(() => accentBgClasses[props.accentColor] ?? accentBgClasses["bauhaus-yellow"]);
const accentBorderClass = computed(
  () => accentBorderClasses[props.accentColor] ?? accentBorderClasses["bauhaus-yellow"],
);
</script>

<template>
  <div
    class="relative border-2 border-ink"
    :class="[
      dimmed ? 'bg-muted text-ink/70' : 'bg-surface text-ink',
      compact ? 'p-4 sm:p-5' : 'p-6 sm:p-8',
      allowOverflow ? 'overflow-visible' : 'overflow-hidden',
      clickable ? 'cursor-pointer transition-transform hover:-translate-y-0.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink' : '',
    ]"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @click="activate"
    @keydown.enter.self.prevent="activate"
  >
    <span v-if="toneClass" class="absolute inset-y-0 left-0 w-1.5" :class="toneClass" aria-hidden="true" />
    <!-- Marks stay small: on a paper surface they read as a mark, where the
         old flood-fill sizes would out-shout the figure they sit beside. -->
    <span
      v-if="accent === 'circle'"
      class="absolute -right-3 -top-3 h-10 w-10 rounded-full sm:h-12 sm:w-12"
      :class="accentBgClass"
      aria-hidden="true"
    />
    <span
      v-else-if="accent === 'square'"
      class="absolute -right-2 -top-2 h-9 w-9 border-2 border-ink sm:h-10 sm:w-10"
      :class="accentBgClass"
      aria-hidden="true"
    />
    <span
      v-else-if="accent === 'triangle'"
      class="absolute right-0 top-0 h-0 w-0 border-b-[34px] border-l-[34px] border-b-transparent sm:border-b-[40px] sm:border-l-[40px]"
      :class="accentBorderClass"
      aria-hidden="true"
    />
    <div class="relative z-10">
      <slot />
    </div>
  </div>
</template>
