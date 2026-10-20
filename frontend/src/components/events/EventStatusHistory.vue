<script setup>
import { STATUS_LABELS } from "@/features/events/dashboard";

defineProps({
  entries: { type: Array, required: true },
});

const formatter = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

function label(status) {
  return STATUS_LABELS[status] ?? status;
}

// A reassignment is not a status change (SCRUM-12): it names the coordinators instead.
function heading(entry) {
  if (entry.kind !== "reassignment") return label(entry.to_status);
  const to = entry.to_coordinator?.full_name ?? "a coordinator";
  return entry.from_coordinator ? `Reassigned to ${to}` : `Assigned to ${to}`;
}
</script>

<template>
  <p v-if="!entries.length" class="text-sm font-medium text-ink/70">No status changes recorded yet.</p>
  <ol v-else class="space-y-4">
    <li v-for="entry in entries" :key="entry.id" class="border-l-4 border-ink pl-4">
      <p class="text-sm font-black uppercase tracking-wide">{{ heading(entry) }}</p>
      <p class="text-xs font-bold text-ink/70">
        by {{ entry.actor?.full_name ?? "Unknown user" }} · {{ formatter.format(new Date(entry.at)) }}
      </p>
      <p v-if="entry.kind === 'reassignment' && entry.from_coordinator" class="mt-1 text-sm font-medium">
        from {{ entry.from_coordinator.full_name }}
      </p>
      <p v-if="entry.reason" class="mt-1 whitespace-pre-wrap text-sm font-medium">{{ entry.reason }}</p>
    </li>
  </ol>
</template>
