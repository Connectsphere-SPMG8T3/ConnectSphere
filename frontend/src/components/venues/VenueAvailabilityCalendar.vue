<script setup>
/**
 * One venue's availability calendar for Venue Staff (SCRUM-57).
 *
 * Day and week views are a time grid, so a booking's setup and turnaround
 * show as their own hatched bands either side of its event time (AC5); the
 * month view draws each entry as a bar across the days it occupies, reusing
 * the dashboard calendar's lane layout. Every date rule lives in
 * `features/venues/availabilityCalendar.js` and `calendar.js`. This component
 * renders what they return and owns only the selected entry; the venue, view
 * and period come from the parent, which asks the API for them.
 */
import { computed, nextTick, ref, watch } from "vue";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  ENTRY_TYPES,
  VIEWS,
  bandLayout,
  entryBadge,
  entryDetails,
  entryTypeMeta,
  formatTime,
  formatWindow,
  layoutDay,
  periodLabel,
  toCalendarEntries,
  viewDayKeys,
} from "@/features/venues/availabilityCalendar";
import { buildMonthGrid, toWeekRows } from "@/features/venues/calendar";
import { singaporeDayKey } from "@/features/venues/singaporeTime";

const props = defineProps({
  calendar: { type: Object, default: null },
  view: { type: String, default: "week" },
  anchorKey: { type: String, required: true },
  isLoading: { type: Boolean, default: false },
  hasLoaded: { type: Boolean, default: false },
  error: { type: String, default: "" },
  /** Injectable for tests; the parent passes a clock that ticks each minute. */
  now: { type: Date, default: () => new Date() },
});

const emit = defineEmits(["select-venue", "set-view", "step", "today", "refresh", "open-day"]);

const entries = computed(() => toCalendarEntries(props.calendar?.entries ?? [], props.now));
const venue = computed(() => props.calendar?.venue ?? null);
const venueOptions = computed(() =>
  (props.calendar?.venues ?? []).map((v) => ({ value: v.id, label: v.is_active ? v.name : `${v.name} (inactive)` })),
);

const dayKeys = computed(() => viewDayKeys(props.view, props.anchorKey));
const todayKey = computed(() => singaporeDayKey(props.now));
const isTimeGrid = computed(() => props.view !== "month");
const title = computed(() => periodLabel(props.view, props.anchorKey));
// A month grid also shows days of the months either side, so compare months.
const isShowingToday = computed(() =>
  props.view === "month"
    ? props.anchorKey.slice(0, 7) === todayKey.value.slice(0, 7)
    : dayKeys.value.includes(todayKey.value),
);

// --- Time grid (day and week) -------------------------------------------------

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const hourLabel = (hour) => `${String(hour).padStart(2, "0")}:00`;
const columnFormatter = new Intl.DateTimeFormat("en-SG", { weekday: "short", day: "numeric", timeZone: "UTC" });
const columnLabel = (key) => columnFormatter.format(new Date(`${key}T00:00:00Z`));

const columns = computed(() =>
  dayKeys.value.map((key) => ({
    key,
    label: columnLabel(key),
    isToday: key === todayKey.value,
    placed: layoutDay(key, entries.value).map((item) => ({ ...item, bands: bandLayout(item.entry, key) })),
  })),
);

// Open on the working day rather than at midnight.
const scroller = ref(null);
const HOUR_REM = 3;
watch(
  [isTimeGrid, () => props.hasLoaded],
  async ([timeGrid, loaded]) => {
    if (!timeGrid || !loaded) return;
    await nextTick();
    if (scroller.value && scroller.value.scrollTop === 0) {
      const rem = Number.parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      scroller.value.scrollTop = 7 * HOUR_REM * rem;
    }
  },
  { immediate: true },
);

// --- Month --------------------------------------------------------------------

const MAX_LANES = 3;
const monthRows = computed(() => {
  if (isTimeGrid.value) return [];
  const [year, month] = props.anchorKey.split("-").map(Number);
  const grid = buildMonthGrid(year, month - 1, entries.value, { today: props.now, weeks: 6 });
  return toWeekRows(grid, { maxLanes: MAX_LANES });
});
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// --- Selection (AC9) ----------------------------------------------------------

const selectedId = ref(null);
const selected = computed(() => entries.value.find((entry) => `${entry.source}-${entry.id}` === selectedId.value));
const details = computed(() => (selected.value ? entryDetails(selected.value) : []));

function select(entry) {
  const id = `${entry.source}-${entry.id}`;
  selectedId.value = selectedId.value === id ? null : id;
}

// A different venue or period has different entries; an entry that vanished
// on refresh (released, expired) simply stops being selected.
watch(
  () => [props.calendar?.venue?.id, props.view, props.anchorKey],
  () => {
    selectedId.value = null;
  },
);

const isEmpty = computed(() => props.hasLoaded && !props.error && venue.value && entries.value.length === 0);

function entryLabel(entry) {
  return `${entryBadge(entry)}: ${entry.label}, ${formatWindow(entry.startsAt, entry.endsAt)}`;
}

// Tailwind's scanner only sees complete class names, so every variant is
// spelled out (frontend/AGENTS.md). Each type differs by pattern or border
// style as well as colour (AC2).
const typeClasses = {
  confirmed: "border-bauhaus-blue bg-bauhaus-blue text-canvas",
  tentative: "border-dashed border-ink bg-bauhaus-yellow/40 text-ink",
  affected: "border-bauhaus-red bg-canvas bg-stripes-red text-ink",
  re_review: "border-bauhaus-blue bg-canvas bg-dots-blue bg-dots text-ink",
  blocked: "border-ink bg-canvas bg-crosshatch text-ink",
};
const swatchClasses = {
  confirmed: "border-bauhaus-blue bg-bauhaus-blue",
  tentative: "border-dashed border-ink bg-bauhaus-yellow/40",
  affected: "border-bauhaus-red bg-canvas bg-stripes-red",
  re_review: "border-bauhaus-blue bg-canvas bg-dots-blue bg-dots",
  blocked: "border-ink bg-canvas bg-crosshatch",
};
const BUFFER_CLASSES = "border-ink/40 bg-canvas bg-hatch text-ink/80";
const classesFor = (entry) => typeClasses[entry.kind] ?? "border-ink bg-canvas text-ink";
</script>

<template>
  <section
    class="flex flex-col gap-4 border-2 border-ink bg-canvas p-4 shadow-hard sm:border-4 sm:p-6"
    aria-labelledby="availability-calendar-heading"
  >
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div class="min-w-0">
        <h2 id="availability-calendar-heading" class="text-2xl font-bold leading-tight">
          {{ title }}
        </h2>
        <p class="mt-1 text-xs font-bold text-ink/60">
          All times in the venue's timezone, Singapore time (Asia/Singapore)
        </p>
      </div>
      <div class="w-full sm:w-72">
        <BauhausSelect
          :model-value="venue?.id ?? ''"
          label="Venue"
          :options="venueOptions"
          :show-placeholder="false"
          compact
          @update:model-value="(id) => emit('select-venue', id)"
        />
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="flex border-2 border-ink" role="group" aria-label="Calendar view">
        <button
          v-for="option in VIEWS"
          :key="option.key"
          type="button"
          class="px-3 py-2 text-xs font-bold active-press"
          :class="view === option.key ? 'bg-ink text-canvas' : 'bg-canvas text-ink hover:bg-muted'"
          :aria-pressed="view === option.key"
          @click="emit('set-view', option.key)"
        >
          {{ option.label }}
        </button>
      </div>
      <button
        type="button"
        class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold enabled:hover:bg-muted active-press disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="isShowingToday"
        @click="emit('today')"
      >
        Today
      </button>
      <button
        type="button"
        class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold hover:bg-muted active-press"
        :aria-label="`Previous ${view}`"
        @click="emit('step', -1)"
      >
        ←
      </button>
      <button
        type="button"
        class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold hover:bg-muted active-press"
        :aria-label="`Next ${view}`"
        @click="emit('step', 1)"
      >
        →
      </button>
      <button
        type="button"
        class="ml-auto border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold enabled:hover:bg-muted active-press disabled:cursor-wait disabled:opacity-60"
        :disabled="isLoading"
        @click="emit('refresh')"
      >
        {{ isLoading ? "Refreshing…" : "Refresh" }}
      </button>
    </div>

    <ul class="flex flex-wrap gap-x-4 gap-y-2" data-testid="calendar-legend">
      <li v-for="type in ENTRY_TYPES" :key="type.key" class="flex items-center gap-2" :title="type.description">
        <span class="h-4 w-6 border-2" :class="swatchClasses[type.key]" aria-hidden="true" />
        <span class="text-xs font-bold text-ink/80">{{ type.label }}</span>
      </li>
      <li class="flex items-center gap-2" title="A booking's setup before and turnaround after its event time">
        <span class="h-4 w-6 border-2" :class="BUFFER_CLASSES" aria-hidden="true" />
        <span class="text-xs font-bold text-ink/80">Setup / turnaround</span>
      </li>
    </ul>

    <p v-if="venue && !venue.is_active" class="border-2 border-ink bg-muted px-3 py-2 text-sm font-medium">
      {{ venue.name }} is inactive. Its existing bookings and blocks still show here.
    </p>
    <p v-if="error" class="border-2 border-bauhaus-red px-3 py-2 text-sm font-bold text-bauhaus-red" role="alert">
      {{ error }}
    </p>
    <BauhausEmptyState
      v-if="isEmpty"
      data-testid="calendar-empty"
      title="Nothing booked, held or blocked"
      :detail="`No bookings, holds or blocks at ${venue.name} in this period.`"
    />
    <p v-else-if="!hasLoaded && !error" class="text-sm font-medium text-ink/60">Loading the calendar…</p>

    <div class="flex flex-col gap-4 lg:flex-row lg:items-start">
      <!-- DAY / WEEK: a column per day, an hour per row. Scrolls inside its own
           box, sideways too on a phone, so the page never does. -->
      <div v-if="isTimeGrid" class="min-w-0 flex-1 overflow-x-auto border-2 border-ink" data-testid="time-grid">
        <div :class="view === 'week' ? 'min-w-[44rem]' : ''">
          <div class="flex border-b-2 border-ink">
            <div class="w-14 shrink-0" />
            <div
              v-for="column in columns"
              :key="column.key"
              class="flex-1 border-l border-ink/15 py-2 text-center text-xs font-bold"
              :class="column.isToday ? 'bg-bauhaus-yellow/30' : ''"
            >
              {{ column.label }}
            </div>
          </div>
          <div ref="scroller" class="h-[32rem] overflow-y-auto">
            <div class="relative flex h-[72rem]">
              <div class="w-14 shrink-0">
                <div v-for="hour in HOURS" :key="hour" class="h-12 pr-2 text-right text-xs font-medium text-ink/55">
                  {{ hourLabel(hour) }}
                </div>
              </div>
              <div
                v-for="column in columns"
                :key="column.key"
                class="relative flex-1 border-l border-ink/15"
                :data-day="column.key"
              >
                <div v-for="hour in HOURS" :key="hour" class="h-12 border-t border-ink/10" aria-hidden="true" />
                <button
                  v-for="item in column.placed"
                  :key="`${item.entry.source}-${item.entry.id}`"
                  type="button"
                  class="absolute overflow-hidden text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ink"
                  :class="selectedId === `${item.entry.source}-${item.entry.id}` ? 'z-10 shadow-hard' : ''"
                  :style="{
                    top: `${item.top}%`,
                    height: `${item.height}%`,
                    left: `calc(${(item.lane / item.lanes) * 100}% + 2px)`,
                    width: `calc(${100 / item.lanes}% - 4px)`,
                  }"
                  :aria-label="entryLabel(item.entry)"
                  :aria-pressed="selectedId === `${item.entry.source}-${item.entry.id}`"
                  data-testid="calendar-entry"
                  :data-type="item.entry.kind"
                  @click="select(item.entry)"
                >
                  <span
                    v-for="band in item.bands"
                    :key="band.part"
                    class="absolute inset-x-0 overflow-hidden border-2 px-1"
                    :class="[
                      band.part === 'event' ? classesFor(item.entry) : BUFFER_CLASSES,
                      band.part === 'event' && item.continuesBefore && band.top === 0 ? 'border-t-0' : '',
                    ]"
                    :style="{ top: `${band.top}%`, height: `${band.height}%` }"
                    :data-band="band.part"
                  >
                    <template v-if="band.part === 'event'">
                      <span class="block truncate text-xs font-bold leading-tight">
                        <span :class="item.entry.kind === 'confirmed' ? '' : 'bg-canvas px-0.5'">{{ entryBadge(item.entry) }}</span>
                      </span>
                      <span class="block truncate text-xs font-medium leading-tight">
                        <span :class="item.entry.kind === 'confirmed' ? '' : 'bg-canvas px-0.5'">{{ item.entry.label }}</span>
                      </span>
                      <span class="block truncate text-xs font-medium leading-tight opacity-80">
                        {{ formatTime(band.startsAt) }}–{{ formatTime(band.endsAt) }}
                      </span>
                    </template>
                    <span v-else class="block truncate text-xs font-bold leading-tight">
                      <span class="bg-canvas px-0.5">{{ band.label }}</span>
                    </span>
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- MONTH: each entry a bar across the days it occupies. -->
      <div v-else class="min-w-0 flex-1 overflow-x-auto border-2 border-ink" data-testid="month-grid">
        <div class="min-w-[36rem]">
          <div class="grid grid-cols-7 border-b-2 border-ink">
            <div v-for="weekday in WEEKDAYS" :key="weekday" class="py-2 text-center text-xs font-bold text-ink/60">
              {{ weekday }}
            </div>
          </div>
          <div
            v-for="(row, rowIndex) in monthRows"
            :key="row.key"
            class="grid min-h-[6.5rem] grid-cols-7 content-start gap-y-1 py-1"
            :class="rowIndex ? 'border-t border-ink/15' : ''"
            :style="{ gridTemplateRows: `auto repeat(${MAX_LANES}, auto) auto` }"
          >
            <button
              v-for="(cell, index) in row.cells"
              :key="`${cell.key}-num`"
              type="button"
              class="mx-1 justify-self-start px-1 text-left text-xs font-bold leading-none hover:bg-muted"
              :class="[cell.inCurrentMonth ? 'text-ink' : 'text-ink/35', cell.isToday ? 'underline decoration-2 underline-offset-4' : '']"
              :style="{ gridColumn: index + 1, gridRow: 1 }"
              :aria-label="`Open ${cell.key} in the day view`"
              @click="emit('open-day', cell.key)"
            >
              {{ cell.day }}
            </button>
            <button
              v-for="segment in row.segments"
              :key="segment.id"
              type="button"
              class="mx-0.5 flex items-center gap-1 overflow-hidden border-2 px-1 py-0.5 text-left text-xs font-bold leading-tight"
              :class="[
                classesFor(segment.item),
                selectedId === `${segment.item.source}-${segment.item.id}` ? 'shadow-hard' : '',
                segment.continuesBefore ? 'border-l-0' : '',
                segment.continuesAfter ? 'border-r-0' : '',
              ]"
              :style="{ gridColumn: `${segment.startIndex + 1} / span ${segment.span}`, gridRow: segment.lane + 2 }"
              :aria-label="entryLabel(segment.item)"
              :aria-pressed="selectedId === `${segment.item.source}-${segment.item.id}`"
              data-testid="calendar-entry"
              :data-type="segment.item.kind"
              @click="select(segment.item)"
            >
              <span class="truncate">
                <span :class="segment.item.kind === 'confirmed' ? '' : 'bg-canvas px-0.5'">
                  {{ entryTypeMeta(segment.item.kind).label }} · {{ segment.item.label }}
                </span>
              </span>
            </button>
            <button
              v-for="(count, index) in row.overflow"
              v-show="count"
              :key="`${row.key}-more-${index}`"
              type="button"
              class="mx-1 justify-self-start px-1 text-left text-xs font-bold text-ink/70 hover:bg-muted"
              :style="{ gridColumn: index + 1, gridRow: MAX_LANES + 2 }"
              @click="emit('open-day', row.cells[index].key)"
            >
              +{{ count }} more
            </button>
          </div>
        </div>
      </div>

      <!-- AC9: what the selected entry is. -->
      <aside class="border-2 border-ink p-4 lg:w-80 lg:shrink-0" aria-live="polite" data-testid="entry-details">
        <template v-if="selected">
          <div class="flex items-start justify-between gap-2">
            <span class="border-2 px-2 py-0.5 text-xs font-bold" :class="classesFor(selected)">
              <span :class="selected.kind === 'confirmed' ? '' : 'bg-canvas px-0.5'">{{ entryBadge(selected) }}</span>
            </span>
            <button
              type="button"
              class="shrink-0 px-1 text-xs font-bold text-ink/60 hover:bg-muted"
              aria-label="Close the details"
              @click="selectedId = null"
            >
              ✕
            </button>
          </div>
          <h3 class="mt-4 text-lg font-bold leading-tight">{{ selected.label }}</h3>
          <dl class="mt-4 flex flex-col gap-4">
            <div v-for="row in details" :key="row.label">
              <dt class="text-sm font-medium text-ink/60">{{ row.label }}</dt>
              <dd class="mt-1 break-words text-sm font-bold">{{ row.value }}</dd>
            </div>
          </dl>
          <RouterLink
            v-if="selected.source === 'booking'"
            :to="{ name: 'booking-request', params: { id: selected.id } }"
            class="mt-4 inline-block border-2 border-ink px-3 py-2 text-xs font-bold hover:bg-muted active-press"
          >
            Open booking request
          </RouterLink>
        </template>
        <p v-else class="text-sm font-medium text-ink/60">Select an entry to see its details.</p>
      </aside>
    </div>
  </section>
</template>
