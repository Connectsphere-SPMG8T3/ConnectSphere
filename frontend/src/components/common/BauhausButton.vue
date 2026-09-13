<script setup>
import { computed } from "vue";

const props = defineProps({
  variant: {
    type: String,
    default: "primary",
    validator: (value) => ["primary", "secondary", "yellow", "outline"].includes(value),
  },
  type: {
    type: String,
    default: "button",
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  fullWidth: {
    type: Boolean,
    default: false,
  },
});

const variantClasses = {
  primary: "bg-bauhaus-red text-canvas",
  secondary: "bg-bauhaus-blue text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  outline: "bg-canvas text-ink",
};

const classes = computed(() => [
  variantClasses[props.variant],
  props.fullWidth ? "w-full" : "",
  props.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer active-press",
]);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="inline-flex items-center justify-center gap-2 border-2 border-ink px-6 py-3 text-sm font-bold uppercase tracking-widest shadow-hard transition-transform sm:border-4"
    :class="classes"
  >
    <slot />
  </button>
</template>
