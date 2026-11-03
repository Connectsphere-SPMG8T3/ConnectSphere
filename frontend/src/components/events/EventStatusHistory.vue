<script setup>
import ChangeRequestChanges from "@/components/events/ChangeRequestChanges.vue";
import { historyEntryText } from "@/features/equipment/technical";
import { fieldLabel } from "@/features/events/amendment";
import { describeChanges } from "@/features/events/changeRequest";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { historyActionLabel } from "@/features/venues/bookingDecision";
import { summariseEditHistoryEntry } from "@/features/venues/venueProfile";

defineProps({
  entries: { type: Array, required: true },
  // SCRUM-81: a list of only reassignments is empty for a different reason than a status history.
  emptyText: { type: String, default: "No status changes recorded yet." },
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
// Neither is a cancellation request (story 84): it carries who asked and why, nor a
// change request (story 32), which also carries what it would change.
// Story 62: an edit, a safety decision, a booking step and a technical update join the
// history; the API sends each role only the entries it may see.
const SAFETY_DECISION_LABELS = {
  approved: "Approved",
  changes_requested: "Changes requested",
  arrangement_rejected: "Arrangement rejected",
  withdrawn: "Withdrawn",
};

// A booking step or technical update with no actor was the system (the expiry job).
const SYSTEM_KINDS = new Set(["booking", "technical"]);

// A venue edit reads as the venue's own History does: only the fields that changed.
function venueChanges(entry) {
  return summariseEditHistoryEntry({ before: entry.old_value, after: entry.new_value });
}

function actorName(entry) {
  return entry.actor?.full_name ?? (SYSTEM_KINDS.has(entry.kind) ? "System" : "Unknown user");
}

function editValue(field, value) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) return "(empty)";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.join(", ");
  if (field.endsWith("_at")) return formatter.format(new Date(value));
  return String(value);
}

function heading(entry) {
  if (entry.kind === "edit") return `${fieldLabel(entry.field)} changed`;
  if (entry.kind === "safety_decision") {
    return `Safety check: ${SAFETY_DECISION_LABELS[entry.decision] ?? entry.decision}`;
  }
  if (entry.kind === "booking") return `${entry.venue_name ?? "A venue"}: ${historyActionLabel(entry.action)}`;
  if (entry.kind === "technical") return `Equipment: ${historyEntryText(entry)}`;
  if (entry.kind === "venue_edit") return `${entry.venue_name ?? "A venue"} details changed`;
  if (entry.kind === "change_requested") return "Change requested";
  if (entry.kind === "change_request_closed") return "Change request closed";
  if (entry.kind === "cancellation_requested") return "Cancellation requested";
  if (entry.kind === "cancellation_rejected") return "Cancellation request rejected";
  if (entry.kind === "change_rejected") return "Change request rejected";
  if (entry.kind === "change_approved") return "Change approved";
  // CR-106: the coordinator's request that a Lead reassign the event, and the Lead's response.
  if (entry.kind === "reassignment_requested") return "Reassignment requested";
  if (entry.kind === "reassignment_declined") return "Reassignment request declined";
  if (entry.kind === "reassignment_request_closed") return "Reassignment request closed";
  if (entry.kind !== "reassignment") return label(entry.to_status);
  const to = entry.to_coordinator?.full_name ?? "a coordinator";
  return entry.from_coordinator ? `Reassigned to ${to}` : `Assigned to ${to}`;
}
</script>

<template>
  <p v-if="!entries.length" class="text-sm font-medium text-ink/70">{{ emptyText }}</p>
  <ol v-else class="space-y-4">
    <li v-for="entry in entries" :key="entry.id" class="border-l-4 border-ink pl-4">
      <p class="text-sm font-bold">{{ heading(entry) }}</p>
      <p class="text-xs font-bold text-ink/70">
        by {{ actorName(entry) }} · {{ formatter.format(new Date(entry.at)) }}
      </p>
      <template v-if="entry.kind === 'edit'">
        <p class="mt-1 whitespace-pre-wrap break-words text-sm font-medium">From: {{ editValue(entry.field, entry.old_value) }}</p>
        <p class="whitespace-pre-wrap break-words text-sm font-medium">To: {{ editValue(entry.field, entry.new_value) }}</p>
      </template>
      <ul v-if="entry.kind === 'venue_edit'" class="mt-1 space-y-1">
        <li v-for="change in venueChanges(entry)" :key="change.field" class="break-words text-sm font-medium">
          {{ change.label }}: {{ change.before }} → {{ change.after }}
        </li>
      </ul>
      <p v-if="entry.kind === 'technical' && entry.detail" class="mt-1 whitespace-pre-wrap text-sm font-medium">{{ entry.detail }}</p>
      <p v-if="entry.kind === 'reassignment' && entry.from_coordinator" class="mt-1 text-sm font-medium">
        from {{ entry.from_coordinator.full_name }}
      </p>
      <ChangeRequestChanges v-if="['change_requested', 'change_approved'].includes(entry.kind) && entry.changes" :rows="describeChanges(entry.changes)" class="mt-2" />
      <p v-if="entry.reason" class="mt-1 whitespace-pre-wrap text-sm font-medium">{{ entry.reason }}</p>
    </li>
  </ol>
</template>
