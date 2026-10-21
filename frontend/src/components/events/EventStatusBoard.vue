<script setup>
import { BOARD_CARD_CLASSES } from "@/features/events/dashboard";

// The status board shared by the coordinator and organiser dashboards: one
// column per status, in workflow order, with a colour legend above. Each
// dashboard renders its own cards through the `card` slot, which receives the
// event, its column and `cardClass` (the base card styling; add a tone from
// `BOARD_CARD_TONE_CLASSES`).
defineProps({
  // [{ status, label, description, events, needsAttention }]
  columns: { type: Array, required: true },
  // The event field that keys each card.
  itemKey: { type: String, default: "event_id" },
});

defineEmits(["open-status"]);

const cardClass = BOARD_CARD_CLASSES;
</script>

<template>
  <ul data-board-legend class="mb-4 flex flex-wrap gap-x-6 gap-y-2 text-sm font-medium">
    <li class="flex items-center gap-2">
      <span aria-hidden="true" class="h-4 w-4 shrink-0 border-2 border-l-8 border-ink border-l-bauhaus-red bg-bauhaus-red/10"></span>
      Red: needs your action
    </li>
    <li class="flex items-center gap-2">
      <span aria-hidden="true" class="h-4 w-4 shrink-0 border-2 border-l-8 border-ink border-l-bauhaus-blue bg-bauhaus-blue/10"></span>
      Blue: you can edit
    </li>
    <li class="flex items-center gap-2">
      <span aria-hidden="true" class="h-4 w-4 shrink-0 border-2 border-l-8 border-ink border-l-ink/40 bg-muted"></span>
      Grey: waiting on others
    </li>
    <li class="flex items-center gap-2">
      <span aria-hidden="true" class="h-4 w-4 shrink-0 border-2 border-l-8 border-ink border-l-bauhaus-green bg-bauhaus-green/10"></span>
      Green: confirmed
    </li>
  </ul>

  <!-- A kanban board: one column per status, in workflow order. The board
       scrolls sideways on narrow screens; each column scrolls its own cards.
       Each column spans the board's two rows through a subgrid, so every
       header grows to the tallest one and the headers stay the same size. -->
  <div class="-mx-4 overflow-x-auto px-4 pb-3 sm:mx-0 sm:px-0">
    <div class="grid auto-cols-[minmax(13rem,1fr)] grid-flow-col grid-rows-[auto_1fr] gap-x-4">
      <div
        v-for="column in columns"
        :key="column.status"
        :data-status-group="column.status"
        class="row-span-2 grid grid-rows-subgrid gap-0 border-2 border-ink bg-canvas shadow-hard sm:border-4"
      >
        <!-- A column holding anything that needs the viewer's attention gets a red header. -->
        <div
          data-column-header
          class="border-b-2 border-ink px-3 pb-3 pt-2 sm:border-b-4"
          :class="column.needsAttention ? 'bg-bauhaus-red text-canvas' : 'bg-muted'"
        >
          <div class="flex items-baseline justify-between gap-3">
            <button
              type="button"
              class="text-left text-sm font-bold underline decoration-2 underline-offset-4 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              :class="column.needsAttention
                ? 'hover:text-bauhaus-yellow focus-visible:outline-canvas'
                : 'hover:text-bauhaus-red focus-visible:outline-ink'"
              :aria-label="`View all ${column.label} events`"
              @click="$emit('open-status', column.status)"
            >
              {{ column.label }}
            </button>
            <p class="text-2xl font-bold">{{ column.events.length }}</p>
          </div>
          <p class="mt-1 text-xs font-medium" :class="column.needsAttention ? 'text-canvas/90' : 'text-ink/70'">
            {{ column.description }}
          </p>
        </div>

        <ul v-if="column.events.length" class="max-h-[26rem] space-y-2 overflow-y-auto p-3">
          <li v-for="event in column.events" :key="event[itemKey]" class="flex">
            <slot name="card" :event="event" :column="column" :card-class="cardClass" />
          </li>
        </ul>

        <p v-else class="p-3 text-sm font-medium text-ink/50">None.</p>
      </div>
    </div>
  </div>
</template>
