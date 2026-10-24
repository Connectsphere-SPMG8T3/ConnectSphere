<script setup>
// Story 32: a change request's changes as "Field: before → after" rows, from
// describeChanges in features/events/changeRequest.js.
defineProps({
  rows: { type: Array, required: true },
});
</script>

<template>
  <ul class="flex flex-col gap-2 border-2 border-ink bg-bauhaus-yellow/20 p-3 text-sm font-medium text-ink">
    <li v-for="row in rows" :key="row.key">
      <span class="font-bold">{{ row.label }}:</span> {{ row.before }} → {{ row.after }}
    </li>
  </ul>
</template>
