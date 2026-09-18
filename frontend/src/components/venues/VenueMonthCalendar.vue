<script setup>
/**
 * Month calendar over every venue's blocks and pending decisions (SCRUM-70).
 *
 * All the date reasoning lives in `features/venues/calendar.js`; this file
 * renders what that returns and owns nothing but the selected day.
 */
import { computed, ref, watch } from "vue";

import {
  CALENDAR_KINDS,
  buildMonthGrid,
  calendarKindMeta,
  canGoPrev as canPageBack,
  defaultMonth,
  sameMonth,
  shiftMonth,
  singaporeMonthOf,
} from "@/features/venues/calendar";
import { blockReasonLabel } from "@/features/venues/dashboard";

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** False until the first load settles, so the grid can say "checking". */
  hasSettled: { type: Boolean, default: false },
  /** Injectable for tests; production always passes the real clock. */
  today: { type: Date, default: () => new Date() },
});

const currentMonth = computed(() => singaporeMonthOf(props.today));
const shown = ref(currentMonth.value);
const selectedDayKey = ref(null);

// Pick the opening month once the payload arrives, not before — on an empty
// list `defaultMonth` answers "this month", which would then stick.
watch(
  () => props.hasSettled,
  (settled) => {
    if (settled) shown.value = defaultMonth(props.items, { today: props.today });
  },
  { immediate: true },
);

const grid = computed(() => buildMonthGrid(shown.value.year, shown.value.month, props.items, { today: props.today }));
const canGoPrev = computed(() => canPageBack(shown.value, { today: props.today }));
const isCurrentMonth = computed(() => sameMonth(shown.value, currentMonth.value));

const monthFormatter = new Intl.DateTimeFormat("en-SG", { month: "long", year: "numeric", timeZone: "UTC" });
const monthLabel = (month) => monthFormatter.format(new Date(Date.UTC(month.year, month.month, 1)));

// Times are stored in UTC and shown in Asia/Singapore (REQUIREMENTS §4).
const dayFormatter = new Intl.DateTimeFormat("en-SG", { dateStyle: "full", timeZone: "Asia/Singapore" });
const timeFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatSelectedDay(key) {
  return dayFormatter.format(new Date(`${key}T00:00:00+08:00`));
}

function formatSpan(item) {
  return `${timeFormatter.format(new Date(item.startsAt))}–${timeFormatter.format(new Date(item.endsAt))}`;
}

function itemLabel(item) {
  return item.kind === "block" ? blockReasonLabel(item.detail) : calendarKindMeta(item.kind).label;
}

function goTo(month) {
  shown.value = month;
  // The selection belonged to the month being left.
  selectedDayKey.value = null;
}

function selectDay(cell) {
  selectedDayKey.value = selectedDayKey.value === cell.key ? null : cell.key;
}

const selectedCell = computed(() =>
  selectedDayKey.value ? grid.value.cells.find((cell) => cell.key === selectedDayKey.value) : null,
);

// Tailwind's scanner only sees complete class names, so every variant is
// spelled out (frontend/AGENTS.md, BauhausCard.vue is the reference).
const dotClasses = {
  red: "bg-bauhaus-red",
  yellow: "bg-bauhaus-yellow",
  blue: "bg-bauhaus-blue",
};

const badgeClasses = {
  red: "bg-bauhaus-red text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  blue: "bg-bauhaus-blue text-canvas",
};

// One day can carry items from all eight venues, so the cell shows a few and
// defers the rest to the day panel below.
const MAX_DOTS = 3;
const visibleDots = (cell) => cell.tones.slice(0, MAX_DOTS);
const overflowCount = (cell) => Math.max(cell.items.length - MAX_DOTS, 0);
</script>

<template>
  <section
    class="flex h-full flex-col border-2 border-ink bg-canvas p-5 shadow-hard sm:border-4 sm:p-6"
    aria-labelledby="venue-calendar-heading"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="venue-calendar-heading" class="text-2xl font-black uppercase leading-none tracking-tighter">
          Calendar
        </h2>
        <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/60">
          {{ monthLabel(shown) }} · Singapore time
        </p>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-widest"
          :class="canGoPrev ? 'bg-canvas active-press' : 'cursor-not-allowed opacity-40'"
          :disabled="!canGoPrev"
          aria-label="Previous month"
          @click="goTo(shiftMonth(shown, -1))"
        >
          ←
        </button>
        <button
          type="button"
          class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold uppercase tracking-widest active-press"
          aria-label="Next month"
          @click="goTo(shiftMonth(shown, 1))"
        >
          →
        </button>
      </div>
    </div>

    <!-- Every block and request is upcoming, so the calendar opens where the
         work actually is. Saying so beats silently moving the user. -->
    <p
      v-if="hasSettled && !isCurrentMonth"
      class="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 border-2 border-dashed border-ink/30 px-3 py-2 text-xs font-medium text-ink/70"
    >
      <span>Showing {{ monthLabel(shown) }} — {{ monthLabel(currentMonth) }} has nothing scheduled.</span>
      <button
        type="button"
        class="font-bold uppercase tracking-widest underline decoration-2 underline-offset-2"
        @click="goTo(currentMonth)"
      >
        Back to this month
      </button>
    </p>

    <ul class="mb-4 flex flex-wrap gap-x-4 gap-y-1">
      <li v-for="kind in CALENDAR_KINDS" :key="kind.key" class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full border border-ink" :class="dotClasses[kind.tone]" aria-hidden="true" />
        <span class="text-[10px] font-bold uppercase tracking-widest text-ink/70">{{ kind.label }}</span>
      </li>
    </ul>

    <div class="grid grid-cols-7 gap-px border-2 border-ink bg-ink">
      <div
        v-for="weekday in grid.weekdays"
        :key="weekday"
        class="bg-canvas py-2 text-center text-[10px] font-bold uppercase tracking-widest text-ink/60"
      >
        {{ weekday }}
      </div>
      <button
        v-for="cell in grid.cells"
        :key="cell.key"
        type="button"
        class="flex min-h-[3.25rem] flex-col items-center justify-start gap-1 bg-canvas py-2 text-center sm:min-h-[4rem]"
        :class="[
          cell.inCurrentMonth ? 'text-ink' : 'text-ink/35',
          selectedDayKey === cell.key ? 'bg-bauhaus-yellow' : '',
          cell.hasItems ? 'cursor-pointer active-press' : 'cursor-default',
        ]"
        :aria-pressed="selectedDayKey === cell.key"
        :aria-label="`${formatSelectedDay(cell.key)}, ${cell.items.length} item${cell.items.length === 1 ? '' : 's'}`"
        @click="selectDay(cell)"
      >
        <span
          class="text-sm font-bold leading-none"
          :class="cell.isToday ? 'border-b-2 border-ink pb-0.5' : ''"
        >
          {{ cell.day }}
        </span>
        <span v-if="cell.hasItems" class="flex items-center gap-0.5">
          <span
            v-for="(tone, index) in visibleDots(cell)"
            :key="`${cell.key}-${tone}-${index}`"
            class="h-1.5 w-1.5 rounded-full"
            :class="dotClasses[tone]"
            aria-hidden="true"
          />
          <span v-if="overflowCount(cell)" class="text-[9px] font-bold leading-none text-ink/60">
            +{{ overflowCount(cell) }}
          </span>
        </span>
      </button>
    </div>

    <div class="mt-4 flex-1">
      <template v-if="selectedCell">
        <p class="text-xs font-bold uppercase tracking-widest text-ink/70">
          {{ formatSelectedDay(selectedCell.key) }}
        </p>
        <ul v-if="selectedCell.hasItems" class="mt-3 flex flex-col gap-2">
          <li
            v-for="item in selectedCell.items"
            :key="`${item.kind}-${item.id}`"
            class="flex flex-wrap items-center gap-2 border-l-4 border-ink bg-surface py-2 pl-3 pr-2"
          >
            <span
              class="border-2 border-ink px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
              :class="badgeClasses[calendarKindMeta(item.kind).tone]"
            >
              {{ itemLabel(item) }}
            </span>
            <span class="text-sm font-bold uppercase tracking-tight">{{ item.venueName }}</span>
            <span class="text-xs font-medium text-ink/70">{{ formatSpan(item) }}</span>
          </li>
        </ul>
        <p v-else class="mt-2 text-sm font-medium text-ink/60">Nothing scheduled.</p>
      </template>
      <p v-else class="text-xs font-medium text-ink/55">
        {{ hasSettled ? "Select a marked day to see what is on it." : "Checking the schedule…" }}
      </p>
    </div>
  </section>
</template>
