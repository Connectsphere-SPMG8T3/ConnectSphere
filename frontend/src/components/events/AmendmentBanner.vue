<script setup>
import { computed } from "vue";

import { fieldLabel } from "@/features/events/amendment";

// SCRUM-33: the coordinator's open amendment request, shown to both sides.
const props = defineProps({
  amendment: { type: Object, required: true },
  // "organiser" (asked to amend) or "coordinator" (waiting on the organiser).
  audience: { type: String, default: "organiser" },
});

const heading = computed(() =>
  props.audience === "coordinator" ? "Waiting for the organiser to amend" : "Your coordinator asked for changes",
);

// Stored UTC, displayed in Asia/Singapore (REQUIREMENTS §4).
const returnedAt = computed(() =>
  new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" })
    .format(new Date(props.amendment.returned_at)),
);
</script>

<template>
  <section data-testid="amendment-banner" class="border-4 border-ink bg-bauhaus-yellow p-6 text-ink shadow-hard sm:p-8">
    <h2 class="text-2xl font-black uppercase tracking-tight">{{ heading }}</h2>
    <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/70">Returned {{ returnedAt }}</p>
    <p class="mt-4 whitespace-pre-wrap font-medium">{{ props.amendment.message }}</p>
    <div v-if="props.amendment.flagged_fields?.length" class="mt-4">
      <p class="text-xs font-bold uppercase tracking-widest">Fields to review</p>
      <ul class="mt-2 flex flex-wrap gap-2">
        <li
          v-for="field in props.amendment.flagged_fields"
          :key="field"
          class="border-2 border-ink bg-canvas px-3 py-1 text-xs font-bold uppercase tracking-wide"
        >
          {{ fieldLabel(field) }}
        </li>
      </ul>
    </div>
    <div v-if="$slots.default" class="mt-6"><slot /></div>
  </section>
</template>
