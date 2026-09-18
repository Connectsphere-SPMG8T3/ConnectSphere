<script setup>
/**
 * Calendar over every venue's blocks and pending decisions (SCRUM-70).
 *
 * Offers a month view (items as labelled bars spanning the days they cover)
 * and a week view (a column per day, listing each item with its time), plus
 * an .ics export. All the date reasoning lives in `features/venues/calendar.js`
 * and the file building in `ics.js`; this file renders what they return and
 * owns nothing but the view mode and the selected day.
 */
import { computed, ref, watch } from "vue";

import {
  CALENDAR_KINDS,
  buildMonthGrid,
  buildWeekGrid,
  calendarKindMeta,
  canGoPrev as canPageBack,
  canGoPrevWeek,
  defaultMonth,
  defaultWeekKey,
  sameMonth,
  shiftMonth,
  shiftWeekKey,
  singaporeMonthOf,
  startOfWeekKey,
  toWeekRows,
} from "@/features/venues/calendar";
import { blockReasonLabel } from "@/features/venues/dashboard";
import { icsFilename, toIcsCalendar } from "@/features/venues/ics";
import { singaporeDayKey } from "@/features/venues/singaporeTime";

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** False until the first load settles, so the grid can say "checking". */
  hasSettled: { type: Boolean, default: false },
  /** Injectable for tests; production always passes the real clock. */
  today: { type: Date, default: () => new Date() },
});

const VIEWS = [
  { key: "month", label: "Month" },
  { key: "week", label: "Week" },
];

const view = ref("month");
const currentMonth = computed(() => singaporeMonthOf(props.today));
const currentWeek = computed(() => startOfWeekKey(props.today));
const shownMonth = ref(currentMonth.value);
const shownWeek = ref(currentWeek.value);
const selectedDayKey = ref(null);

// Pick the opening period once the payload arrives, not before — on an empty
// list the defaults answer "now", which would then stick.
watch(
  () => props.hasSettled,
  (settled) => {
    if (!settled) return;
    shownMonth.value = defaultMonth(props.items, { today: props.today });
    shownWeek.value = defaultWeekKey(props.items, { today: props.today });
  },
  { immediate: true },
);

const isWeekView = computed(() => view.value === "week");

// Month: six rows always, so the panel is the same height in every month.
const grid = computed(() =>
  isWeekView.value
    ? buildWeekGrid(shownWeek.value, props.items, { today: props.today })
    : buildMonthGrid(shownMonth.value.year, shownMonth.value.month, props.items, {
        today: props.today,
        weeks: 6,
      }),
);

/**
 * How many bars a month cell shows before it starts counting instead. Two,
 * plus a "+n" line, is what fits in a sixth of the panel's fixed height.
 */
const MAX_LANES = 2;

const monthRows = computed(() => (isWeekView.value ? [] : toWeekRows(grid.value, { maxLanes: MAX_LANES })));

const canGoPrev = computed(() =>
  isWeekView.value
    ? canGoPrevWeek(shownWeek.value, { today: props.today })
    : canPageBack(shownMonth.value, { today: props.today }),
);

const isCurrentPeriod = computed(() =>
  isWeekView.value ? shownWeek.value === currentWeek.value : sameMonth(shownMonth.value, currentMonth.value),
);

const monthFormatter = new Intl.DateTimeFormat("en-SG", { month: "long", year: "numeric", timeZone: "UTC" });
const monthLabel = (month) => monthFormatter.format(new Date(Date.UTC(month.year, month.month, 1)));

const rangeFormatter = new Intl.DateTimeFormat("en-SG", { day: "numeric", month: "short", timeZone: "UTC" });

/** What the header names: a month, or the week's date range. */
const periodLabel = computed(() => {
  if (!isWeekView.value) return monthLabel(shownMonth.value);
  const from = rangeFormatter.format(new Date(`${grid.value.startKey}T00:00:00Z`));
  const to = rangeFormatter.format(new Date(`${grid.value.endKey}T00:00:00Z`));
  return `${from} – ${to} ${grid.value.endKey.slice(0, 4)}`;
});

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

function step(delta) {
  if (isWeekView.value) shownWeek.value = shiftWeekKey(shownWeek.value, delta);
  else shownMonth.value = shiftMonth(shownMonth.value, delta);
  // The selection belonged to the period being left.
  selectedDayKey.value = null;
}

function goToToday() {
  shownMonth.value = currentMonth.value;
  shownWeek.value = currentWeek.value;
  selectedDayKey.value = null;
}

/**
 * Switching view keeps the user where they were rather than snapping back to
 * now: month to week anchors on the selected day, or the shown month's first
 * day; week to month opens the month the shown week sits in.
 */
function setView(next) {
  if (next === view.value) return;
  if (next === "week") {
    shownWeek.value = startOfWeekKey(selectedDayKey.value ?? anchorDayKeyForShownMonth());
  } else {
    shownMonth.value = singaporeMonthOf(new Date(`${selectedDayKey.value ?? shownWeek.value}T00:00:00+08:00`));
  }
  view.value = next;
}

/**
 * Which day the week view should open on, coming from the month view.
 *
 * Today if the shown month is the current one; otherwise the month's first
 * day that carries something, so switching lands on work rather than on an
 * empty first week — the same reasoning that picks the opening month. Falls
 * back to the 1st when the month is empty.
 */
function anchorDayKeyForShownMonth() {
  if (sameMonth(shownMonth.value, currentMonth.value)) return singaporeDayKey(props.today);
  const firstMarked = grid.value.cells.find((cell) => cell.hasItems && cell.inCurrentMonth);
  if (firstMarked) return firstMarked.key;
  const { year, month } = shownMonth.value;
  return `${year}-${String(month + 1).padStart(2, "0")}-01`;
}

function selectDay(cell) {
  selectedDayKey.value = selectedDayKey.value === cell.key ? null : cell.key;
}

const selectedCell = computed(() =>
  selectedDayKey.value ? grid.value.cells.find((cell) => cell.key === selectedDayKey.value) : null,
);

// Tailwind's scanner only sees complete class names, so every variant is
// spelled out (frontend/AGENTS.md, BauhausCard.vue is the reference).

// Still used by the legend.
const dotClasses = {
  red: "bg-bauhaus-red",
  yellow: "bg-bauhaus-yellow",
  blue: "bg-bauhaus-blue",
};

// Month-view bars: a tinted body behind a solid leading edge, so a run of days
// reads as one object and its kind stays legible at a glance.
const barClasses = {
  red: "border-bauhaus-red bg-bauhaus-red/15 text-ink",
  yellow: "border-bauhaus-yellow bg-bauhaus-yellow/25 text-ink",
  blue: "border-bauhaus-blue bg-bauhaus-blue/15 text-ink",
};

const badgeClasses = {
  red: "bg-bauhaus-red text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  blue: "bg-bauhaus-blue text-canvas",
};

// Week-view entries are small, so the kind is carried by a coloured edge
// rather than a badge that would crowd out the venue name.
const itemStripeClasses = {
  red: "border-l-bauhaus-red bg-bauhaus-red/10",
  yellow: "border-l-bauhaus-yellow bg-bauhaus-yellow/15",
  blue: "border-l-bauhaus-blue bg-bauhaus-blue/10",
};

/** Just the start time, for a bar too narrow to carry a full span. */
const formatStart = (item) => timeFormatter.format(new Date(item.startsAt));

/**
 * Download everything the dashboard holds as an .ics file.
 *
 * The whole payload, not the month on screen: the point of exporting is to
 * carry your schedule into the calendar app you already use, and a staff
 * member who exported "just October" would be missing November's blocks
 * without being told.
 */
function exportCalendar() {
  const ics = toIcsCalendar(props.items, { now: new Date() });
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = icsFilename(new Date());
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Releasing it immediately can cancel the download in some browsers, so let
  // the click be handled first.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
</script>

<template>
  <!-- A definite height, not a minimum. `overflow-y-auto` on the day list only
       engages when its container's height is fixed; under a min-height the
       panel would still grow to fit a busy day, stretching the stat tiles
       beside it and pushing the lists below it down. -->
  <section
    class="flex h-[36rem] flex-col border-2 border-ink bg-canvas p-5 shadow-hard sm:h-[40rem] sm:border-4 sm:p-6"
    aria-labelledby="venue-calendar-heading"
  >
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="venue-calendar-heading" class="text-2xl font-black uppercase leading-none tracking-tighter">
          Calendar
        </h2>
        <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/60">
          {{ periodLabel }} · Singapore time
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <div class="flex border-2 border-ink" role="group" aria-label="Calendar view">
          <button
            v-for="option in VIEWS"
            :key="option.key"
            type="button"
            class="px-3 py-2 text-xs font-bold uppercase tracking-widest active-press"
            :class="view === option.key ? 'bg-ink text-canvas' : 'bg-canvas text-ink'"
            :aria-pressed="view === option.key"
            @click="setView(option.key)"
          >
            {{ option.label }}
          </button>
        </div>
        <button
          type="button"
          class="border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-widest"
          :class="isCurrentPeriod ? 'cursor-not-allowed opacity-40' : 'bg-canvas active-press'"
          :disabled="isCurrentPeriod"
          :aria-label="isWeekView ? 'Jump to the current week' : 'Jump to the current month'"
          @click="goToToday"
        >
          Today
        </button>
        <button
          type="button"
          class="border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-widest"
          :class="canGoPrev ? 'bg-canvas active-press' : 'cursor-not-allowed opacity-40'"
          :disabled="!canGoPrev"
          :aria-label="isWeekView ? 'Previous week' : 'Previous month'"
          @click="step(-1)"
        >
          ←
        </button>
        <button
          type="button"
          class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold uppercase tracking-widest active-press"
          :aria-label="isWeekView ? 'Next week' : 'Next month'"
          @click="step(1)"
        >
          →
        </button>
        <button
          type="button"
          class="border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-widest"
          :class="items.length ? 'bg-canvas active-press' : 'cursor-not-allowed opacity-40'"
          :disabled="!items.length"
          aria-label="Export every block and pending request as a calendar file"
          @click="exportCalendar"
        >
          Export
        </button>
      </div>
    </div>

    <ul class="mb-4 flex flex-wrap gap-x-4 gap-y-1">
      <li v-for="kind in CALENDAR_KINDS" :key="kind.key" class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full border border-ink" :class="dotClasses[kind.tone]" aria-hidden="true" />
        <span class="text-[10px] font-bold uppercase tracking-widest text-ink/70">{{ kind.label }}</span>
      </li>
    </ul>

    <!-- Grid on the left, the selected day's detail on the right, both filling
         the panel's fixed height. The grid's six week rows are `1fr`, so they
         share whatever height is left rather than sitting at a fixed size and
         leaving dead space under the calendar. Stacks on narrow screens. -->
    <div class="flex min-h-0 flex-1 flex-col gap-5 lg:flex-row lg:gap-6">
      <div class="flex min-h-0 flex-1 flex-col border-2 border-ink">
        <div class="grid shrink-0 grid-cols-7 border-b-2 border-ink">
          <div
            v-for="weekday in grid.weekdays"
            :key="weekday"
            class="py-2 text-center text-[10px] font-bold uppercase tracking-widest text-ink/60"
          >
            {{ weekday }}
          </div>
        </div>

        <!-- MONTH: one row per week. A booking or block runs over a continuous
             stretch of days, so it is drawn as a single bar spanning those
             columns — a fortnight's renovation should read as one thing, not
             as fourteen identical chips. That means the day cells cannot use a
             grid gap (a bar has to cross it), so the click targets sit in a
             layer behind and the bars are drawn over them. -->
        <div v-if="!isWeekView" class="grid min-h-0 flex-1" :style="{ gridTemplateRows: `repeat(${monthRows.length}, minmax(0, 1fr))` }">
          <div
            v-for="(row, rowIndex) in monthRows"
            :key="row.key"
            class="relative min-h-0"
            :class="rowIndex ? 'border-t border-ink/15' : ''"
          >
            <div class="absolute inset-0 grid grid-cols-7">
              <button
                v-for="(cell, index) in row.cells"
                :key="cell.key"
                type="button"
                class="min-w-0"
                :class="[
                  index ? 'border-l border-ink/15' : '',
                  selectedDayKey === cell.key ? 'bg-bauhaus-yellow/40' : '',
                  cell.hasItems ? 'cursor-pointer' : 'cursor-default',
                ]"
                :aria-pressed="selectedDayKey === cell.key"
                :aria-label="`${formatSelectedDay(cell.key)}, ${cell.items.length} item${cell.items.length === 1 ? '' : 's'}`"
                @click="selectDay(cell)"
              />
            </div>

            <!-- Drawn over the click layer, and transparent to the pointer so
                 clicking a bar still selects the day underneath it. -->
            <div
              class="pointer-events-none relative grid h-full grid-cols-7 content-start gap-y-0.5 overflow-hidden px-0.5 py-1"
              :style="{ gridTemplateRows: `auto repeat(${MAX_LANES}, auto) auto` }"
            >
              <span
                v-for="(cell, index) in row.cells"
                :key="`${cell.key}-num`"
                class="px-1 text-left text-[11px] font-bold leading-none"
                :class="cell.inCurrentMonth ? 'text-ink' : 'text-ink/35'"
                :style="{ gridColumn: index + 1, gridRow: 1 }"
              >
                <span :class="cell.isToday ? 'border-b-2 border-ink pb-0.5' : ''">{{ cell.day }}</span>
              </span>

              <span
                v-for="segment in row.segments"
                :key="segment.id"
                class="mx-0.5 flex items-center gap-1 overflow-hidden px-1 py-0.5 text-[10px] font-bold leading-tight"
                :class="[
                  barClasses[calendarKindMeta(segment.item.kind).tone],
                  segment.continuesBefore ? 'rounded-l-none border-l-0 pl-0.5' : 'border-l-4',
                ]"
                :style="{ gridColumn: `${segment.startIndex + 1} / span ${segment.span}`, gridRow: segment.lane + 2 }"
              >
                <span class="truncate">{{ segment.item.venueName }}</span>
                <span v-if="segment.span === 1" class="ml-auto shrink-0 font-medium opacity-70">
                  {{ formatStart(segment.item) }}
                </span>
                <span v-else-if="segment.continuesAfter" class="ml-auto shrink-0 opacity-60" aria-hidden="true">›</span>
              </span>

              <span
                v-for="(count, index) in row.overflow"
                :key="`${row.key}-more-${index}`"
                v-show="count"
                class="px-1 text-left text-[9px] font-bold uppercase tracking-widest text-ink/55"
                :style="{ gridColumn: index + 1, gridRow: MAX_LANES + 2 }"
              >
                +{{ count }}
              </span>
            </div>
          </div>
        </div>

        <!-- WEEK: a column per day, tall enough to name every item on it. -->
        <div v-else class="grid min-h-0 flex-1 grid-cols-7">
          <button
            v-for="(cell, index) in grid.cells"
            :key="cell.key"
            type="button"
            class="flex min-h-0 min-w-0 flex-col items-stretch gap-1 overflow-hidden px-1 py-2 text-center"
            :class="[
              index ? 'border-l border-ink/15' : '',
              selectedDayKey === cell.key ? 'bg-bauhaus-yellow/40' : '',
              cell.hasItems ? 'cursor-pointer' : 'cursor-default',
            ]"
            :aria-pressed="selectedDayKey === cell.key"
            :aria-label="`${formatSelectedDay(cell.key)}, ${cell.items.length} item${cell.items.length === 1 ? '' : 's'}`"
            @click="selectDay(cell)"
          >
            <span class="shrink-0 text-sm font-bold leading-none" :class="cell.isToday ? 'underline decoration-2 underline-offset-4' : ''">
              {{ cell.day }}
            </span>
            <span v-if="cell.hasItems" class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
              <span
                v-for="item in cell.items"
                :key="`${item.kind}-${item.id}`"
                class="flex shrink-0 flex-col gap-0.5 border-l-4 px-1 py-1 text-left"
                :class="itemStripeClasses[calendarKindMeta(item.kind).tone]"
              >
                <span class="text-[10px] font-bold uppercase leading-tight tracking-tight">{{ item.venueName }}</span>
                <span class="text-[9px] font-medium leading-tight text-ink/65">{{ formatSpan(item) }}</span>
              </span>
            </span>
          </button>
        </div>
      </div>

      <!-- Keeps its size whether or not a day is selected, so picking one never
           reflows the grid beside it. Scrolls internally on a busy day rather
           than growing the panel. -->
      <div
        class="flex h-40 min-h-0 shrink-0 flex-col border-t-2 border-ink/15 pt-4 lg:h-auto lg:w-72 lg:self-stretch lg:border-l-2 lg:border-t-0 lg:pl-6 lg:pt-0"
      >
        <template v-if="selectedCell">
          <div class="flex shrink-0 items-start justify-between gap-2">
            <p class="text-xs font-bold uppercase tracking-widest text-ink/70">
              {{ formatSelectedDay(selectedCell.key) }}
            </p>
            <button
              type="button"
              class="shrink-0 text-xs font-bold uppercase leading-none tracking-widest text-ink/50"
              aria-label="Clear the selected day"
              @click="selectedDayKey = null"
            >
              ✕
            </button>
          </div>
          <ul v-if="selectedCell.hasItems" class="mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
            <li
              v-for="item in selectedCell.items"
              :key="`${item.kind}-${item.id}`"
              class="flex shrink-0 flex-col gap-1 border-l-4 border-ink bg-surface py-2 pl-3 pr-2"
            >
              <span
                class="self-start border-2 border-ink px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
                :class="badgeClasses[calendarKindMeta(item.kind).tone]"
              >
                {{ itemLabel(item) }}
              </span>
              <span class="text-sm font-bold uppercase leading-tight tracking-tight">{{ item.venueName }}</span>
              <span class="text-xs font-medium text-ink/70">{{ formatSpan(item) }}</span>
            </li>
          </ul>
          <p v-else class="mt-2 text-sm font-medium text-ink/60">Nothing scheduled.</p>
        </template>
        <p v-else class="text-xs font-medium text-ink/55">
          {{ hasSettled ? "Select a marked day to see what is on it." : "Checking the schedule…" }}
        </p>
      </div>
    </div>
  </section>
</template>
