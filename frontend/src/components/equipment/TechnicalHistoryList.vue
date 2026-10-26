<script setup>
import { formatTechnicalTime, historyActor, historyEntryText } from "@/features/equipment/technical";

// SCRUM-24 AC13, SCRUM-44 AC8: an event's equipment history, newest first, on
// Technical Support's event page and the coordinator's Equipment request panel.
defineProps({
  entries: { type: Array, required: true },
});
</script>

<template>
  <p v-if="!entries.length" class="mt-4 text-sm">Nothing recorded yet.</p>
  <ol v-else class="mt-4 flex flex-col gap-3">
    <li v-for="(entry, index) in entries" :key="index" class="border-l-4 border-ink pl-3">
      <p class="text-sm font-bold">{{ historyEntryText(entry) }}</p>
      <p v-if="entry.detail" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{{ entry.detail }}</p>
      <p class="text-xs font-bold text-ink/60">{{ historyActor(entry) }} · {{ formatTechnicalTime(entry.created_at) }}</p>
    </li>
  </ol>
</template>
