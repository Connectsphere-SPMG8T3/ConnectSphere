<script setup>
/**
 * One assigned event on the coordinator's Events view: the whole card opens the
 * event's review page. Coloured like the Overview's status board (red needs the
 * coordinator, grey is with someone else, green is confirmed). A past event is
 * shown as confirmed without its action, since nothing can be done about it; a
 * rejected request (status `rejected`) is grey, with no arrangements footer.
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";

import {
  ACTION_BADGE_CLASSES,
  BOARD_CARD_TONE_CLASSES,
  STATUS_LABELS,
  actionKindMeta,
  boardEventTone,
  flagLabel,
  formatEventDateTime,
} from "@/features/events/dashboard";

const props = defineProps({
  // A card from `coordinatorEventCards`.
  card: { type: Object, required: true },
  past: { type: Boolean, default: false },
});

const isRejected = computed(() => props.card.status === "rejected");
const actionKind = computed(() => (props.past || isRejected.value ? null : props.card.actionKind));
const tone = computed(() => {
  if (isRejected.value) return "rejected";
  if (props.past) return "done";
  return boardEventTone({ status: props.card.status, topAction: actionKind.value });
});
</script>

<template>
  <RouterLink
    :to="{ name: 'coordinator-event', params: { id: card.id } }"
    data-event-card
    :data-tone="tone"
    :aria-label="`More details about ${card.name}`"
    class="group flex w-full flex-col border-2 border-l-8 border-ink p-4 transition duration-150 hover:-translate-y-0.5 hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink motion-reduce:transition-none"
    :class="BOARD_CARD_TONE_CLASSES[tone]"
  >
    <p class="text-sm text-ink/75">
      {{ STATUS_LABELS[card.status] }} · {{ formatEventDateTime(card.startsAt) }}
    </p>
    <h3 class="mt-1 text-lg font-bold leading-snug">{{ card.name }}</h3>

    <div v-if="actionKind || card.flags.length" class="mt-3 flex flex-wrap gap-2">
      <span
        v-if="actionKind"
        data-action-badge
        class="border-2 border-ink px-2 py-0.5 text-xs font-medium"
        :class="ACTION_BADGE_CLASSES[actionKindMeta(actionKind).tone]"
      >
        {{ actionKindMeta(actionKind).label }}
      </span>
      <span
        v-for="flag in card.flags"
        :key="flag"
        class="bg-bauhaus-red px-2 py-0.5 text-xs font-medium text-canvas"
      >
        {{ flagLabel(flag) }}
      </span>
    </div>

    <div v-if="!isRejected" data-card-footer class="mt-auto flex items-end justify-between gap-3 pt-4">
      <div v-if="card.outstanding.length" class="flex flex-wrap items-center gap-1.5">
        <span class="text-xs text-ink/75">Outstanding</span>
        <span
          v-for="item in card.outstanding"
          :key="item"
          data-outstanding
          class="border border-ink bg-canvas px-1.5 py-0.5 text-xs font-medium"
        >
          {{ item }}
        </span>
      </div>
      <p v-else class="text-xs font-medium text-bauhaus-green">All arrangements in place</p>
      <span
        aria-hidden="true"
        class="shrink-0 text-sm font-bold transition-transform group-hover:translate-x-0.5"
      >
        More details →
      </span>
    </div>
  </RouterLink>
</template>
