<script setup>
/**
 * The honest "nothing here" panel. Used wherever a widget's data source exists
 * but has returned nothing, and wherever a feature has not shipped yet — the
 * dashboard says which, rather than showing a plausible-looking number.
 */
defineProps({
  title: { type: String, required: true },
  detail: { type: String, default: "" },
});
</script>

<template>
  <div
    class="flex flex-col items-start gap-1 border-2 border-dashed border-ink/30 bg-surface px-5 py-6"
  >
    <p class="text-xs font-bold uppercase tracking-widest text-ink/70">{{ title }}</p>
    <p v-if="detail" class="max-w-prose text-sm font-medium text-ink/60">{{ detail }}</p>
  </div>
</template>
