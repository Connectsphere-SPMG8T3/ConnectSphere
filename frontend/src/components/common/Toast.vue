<script setup>
import { computed } from "vue";

import { dismissToast, toastState } from "@/composables/useToast";

const toneClasses = {
  success: "border-ink bg-bauhaus-yellow text-ink",
  error: "border-ink bg-bauhaus-red text-canvas",
};

const toastClasses = computed(() => toneClasses[toastState.value?.tone] ?? toneClasses.success);
</script>

<template>
  <div
    v-if="toastState"
    class="fixed inset-x-4 bottom-4 z-50 sm:left-auto sm:right-6 sm:max-w-md"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-start gap-4 border-2 px-4 py-3 shadow-hard sm:border-4" :class="toastClasses">
      <p class="min-w-0 flex-1 text-sm font-bold uppercase tracking-wide">{{ toastState.message }}</p>
      <button
        type="button"
        class="shrink-0 text-xl font-black leading-none"
        aria-label="Dismiss notification"
        @click="dismissToast"
      >
        &times;
      </button>
    </div>
  </div>
</template>
