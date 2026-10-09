<script setup>
import { displaySafetyTime } from "@/features/events/safetyDecision";

defineProps({ decision: { type: Object, required: true } });
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
    <p v-if="decision.affected_booking_ids?.length" class="mt-3 text-sm">Affected bookings: {{ decision.affected_booking_ids.length }}
      <span v-if="decision.decision === 'arrangement_rejected'" class="block font-bold">Rejected by the Safety Officer</span></p>
    <p v-if="decision.affected_equipment_request_ids?.length" class="mt-3 text-sm">Affected equipment requests: {{ decision.affected_equipment_request_ids.length }}</p>
  </div>
</template>
