<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";

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
  // "sm" for secondary placements such as a page header's actions, where the
  // standard size would outweigh the title.
  // A route location. When set the button renders as a link, for actions that
  // navigate rather than submit; `type` and `disabled` then don't apply.
  to: {
    type: [String, Object],
    default: null,
  },
  size: {
    type: String,
    default: "md",
    validator: (value) => ["md", "sm"].includes(value),
  },
});

const variantClasses = {
  primary: "bg-bauhaus-red text-canvas",
  secondary: "bg-bauhaus-blue text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  outline: "bg-canvas text-ink",
};

const sizeClasses = {
  md: "px-6 py-3 text-sm sm:border-4",
  sm: "px-4 py-2 text-xs",
};

const classes = computed(() => [
  "inline-flex items-center justify-center gap-2 border-2 border-ink font-bold shadow-hard transition-transform",
  variantClasses[props.variant],
  sizeClasses[props.size],
  props.fullWidth ? "w-full" : "",
  props.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-muted hover:text-ink active-press",
]);
</script>

<template>
  <RouterLink v-if="to" :to="to" :class="classes">
    <slot />
  </RouterLink>
  <button v-else :type="type" :disabled="disabled" :class="classes">
    <slot />
  </button>
</template>
