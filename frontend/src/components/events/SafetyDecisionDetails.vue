<script setup>
import { computed } from "vue";
import { displaySafetyTime } from "@/features/events/safetyDecision";

const props = defineProps({ decision: { type: Object, required: true } });
const rejectedVenues = computed(() => (props.decision.rejected_venues ?? [])
  .map((venue) => venue.venue_name ?? "a venue that no longer exists").join(" · "));
const concerns = computed(() => [
  ...(props.decision.affected_bookings ?? []).map((booking) => booking.venue_name ?? "a booking that no longer exists"),
  ...(props.decision.affected_equipment ?? []).map((line) => line.equipment_name ?? "an equipment request that no longer exists"),
].join(" · "));
const labels = {
  approved: "Approved",
  changes_requested: "Changes requested",
  arrangement_rejected: "Arrangement rejected",
  withdrawn: "Withdrawn",
};
</script>

<template>
  <div class="break-words">
    <p class="font-bold">{{ labels[decision.decision] ?? decision.decision }}</p>
    <p class="mt-2 text-sm">{{ decision.decided_by_name ?? 'System' }} · {{ displaySafetyTime(decision.decided_at) }}</p>
    <p v-if="decision.comment" class="mt-3 whitespace-pre-wrap">{{ decision.comment }}</p>
    <p v-if="rejectedVenues" class="mt-3 text-sm">Rejected venue: {{ rejectedVenues }}</p>
    <p v-if="decision.decision !== 'arrangement_rejected' && concerns" class="mt-3 text-sm">Concerns: {{ concerns }}</p>
    <div v-if="decision.decision === 'arrangement_rejected' && decision.revision" class="mt-3 border-2 border-ink p-3">
      <p class="text-sm font-bold">Coordinator's response:</p>
      <p class="mt-2 whitespace-pre-wrap">{{ decision.revision.note }}</p>
      <p class="mt-2 text-sm">{{ decision.revision.by_name ?? 'Coordinator' }} · {{ displaySafetyTime(decision.revision.at) }}</p>
    </div>
  </div>
</template>
