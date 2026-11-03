<script setup>
import { computed } from "vue";
import { displaySafetyTime } from "@/features/events/safetyDecision";
import { factorLabel, ratingLabel } from "@/features/events/safetyChecklist";

const props = defineProps({ decision: { type: Object, required: true } });
const rejectedVenues = computed(() => (props.decision.rejected_venues ?? [])
  .map((venue) => venue.venue_name ?? "a venue that no longer exists").join(" · "));
const concerns = computed(() => [
  ...(props.decision.affected_bookings ?? []).map((booking) => booking.venue_name ?? "a booking that no longer exists"),
  ...(props.decision.affected_equipment ?? []).map((line) => line.equipment_name ?? "an equipment request that no longer exists"),
].join(" · "));
// CR-108 AC6: the recorded marks, grouped by venue in the order recorded, then the whole event.
const checklistSections = computed(() => {
  const marks = props.decision.checklist ?? [];
  const venues = new Map();
  for (const mark of marks.filter((m) => m.booking_id)) {
    if (!venues.has(mark.booking_id)) venues.set(mark.booking_id, { title: mark.venue_name ?? "a venue that no longer exists", marks: [] });
    venues.get(mark.booking_id).marks.push(mark);
  }
  const event = marks.filter((m) => !m.booking_id);
  return [...venues.values(), ...(event.length ? [{ title: "Whole event", marks: event }] : [])];
});
const hasConcern = computed(() => (props.decision.checklist ?? []).some((mark) => mark.rating === "concern"));
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
    <div v-if="decision.organiser_comment" class="mt-3">
      <p class="text-sm font-bold">Comment for the organiser</p>
      <p class="mt-1 whitespace-pre-wrap">{{ decision.organiser_comment }}</p>
    </div>
    <div v-if="decision.private_note" class="mt-3 border-l-4 border-ink pl-3">
      <p class="text-sm font-bold">Private notes <span class="font-medium">(Not shown to the organiser)</span></p>
      <p class="mt-1 whitespace-pre-wrap">{{ decision.private_note }}</p>
    </div>
    <p v-if="rejectedVenues" class="mt-3 text-sm">Rejected venue: {{ rejectedVenues }}</p>
    <p v-if="decision.decision !== 'arrangement_rejected' && concerns" class="mt-3 text-sm">Concerns: {{ concerns }}</p>
    <details v-if="checklistSections.length" :open="hasConcern" class="mt-3 border-2 border-ink p-3">
      <summary class="cursor-pointer text-sm font-bold">Checklist</summary>
      <section v-for="section in checklistSections" :key="section.title" class="mt-3">
        <h4 class="text-sm font-bold">{{ section.title }}</h4>
        <ul class="mt-1 space-y-1 text-sm">
          <li v-for="mark in section.marks" :key="mark.factor" :class="mark.rating === 'concern' ? 'font-bold' : ''">
            {{ factorLabel(mark.factor) }}: {{ ratingLabel(mark.rating) }}<span v-if="mark.note" class="whitespace-pre-wrap font-medium"> — {{ mark.note }}</span>
          </li>
        </ul>
      </section>
    </details>
    <div v-if="decision.decision === 'arrangement_rejected' && decision.revision" class="mt-3 border-2 border-ink p-3">
      <p class="text-sm font-bold">Coordinator's response:</p>
      <p class="mt-2 whitespace-pre-wrap">{{ decision.revision.note }}</p>
      <p class="mt-2 text-sm">{{ decision.revision.by_name ?? 'Coordinator' }} · {{ displaySafetyTime(decision.revision.at) }}</p>
    </div>
  </div>
</template>
