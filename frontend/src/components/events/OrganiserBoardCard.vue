<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";

import { ACTION_BADGE_CLASSES, BOARD_CARD_CLASSES, BOARD_CARD_TONE_CLASSES, STATUS_LABELS } from "@/features/events/dashboard";
import { getOrganiserAction, organiserBoardTone } from "@/features/events/organiserDashboard";

// One of the organiser's events as a status-board card: on the board itself and
// in the Past and Rejected sections below it. A whole-card link to the event
// (or, for a draft or returned request, its form), toned by
// `organiserBoardTone`; a returned request carries its action badge.
const props = defineProps({
  event: { type: Object, required: true },
  // The formatted date, time and timezone line.
  schedule: { type: String, required: true },
  // Show the status under the name, for sections that mix statuses.
  showStatus: { type: Boolean, default: false },
});

const tone = computed(() => organiserBoardTone(props.event));
// Drafts and returned requests open on the request form, as on the Events tab (SCRUM-33).
const target = computed(() =>
  getOrganiserAction(props.event).kind === "view"
    ? { name: "event-detail", params: { id: props.event.id } }
    : { name: "event-new", query: { id: props.event.id } },
);
</script>

<template>
  <RouterLink
    :to="target"
    :data-event-row="event.id"
    :data-tone="tone"
    :class="[BOARD_CARD_CLASSES, BOARD_CARD_TONE_CLASSES[tone]]"
    :aria-label="`Open ${event.name}`"
  >
    <p class="text-sm font-bold">{{ event.name }}</p>
    <p v-if="showStatus" class="text-xs font-bold">{{ STATUS_LABELS[event.status] }}</p>
    <p class="text-xs text-ink/75">{{ schedule }}</p>
    <p
      v-if="event.status === 'returned'"
      class="mt-1 inline-block border-2 border-ink px-2 py-0.5 text-xs font-medium"
      :class="ACTION_BADGE_CLASSES.red"
    >
      {{ getOrganiserAction(event).label }}
    </p>
  </RouterLink>
</template>
