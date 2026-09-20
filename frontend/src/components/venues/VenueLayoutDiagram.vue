<script setup>
/**
 * A schematic of one room layout (SCRUM-67, VC-R8).
 *
 * Drawn from `venue_layouts`, which is real data, but it is a **schematic of
 * the arrangement, not this room's floor plan** — we do not hold the venue's
 * geometry, so the proportions, aisles and table positions here are generic.
 * The caller labels it as such; the `<title>` says so too, for screen readers.
 *
 * Geometry is computed rather than hand-drawn so the six layouts stay
 * consistent with each other and a seventh is a single entry below.
 */
import { computed } from "vue";

const props = defineProps({
  layout: { type: String, required: true },
  label: { type: String, default: "" },
});

const W = 320;
const H = 180;

const grid = (xs, ys) => ys.flatMap((cy) => xs.map((cx) => ({ cx, cy })));
const ring = (cx, cy, radius, count) =>
  Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    return { cx: cx + Math.cos(angle) * radius, cy: cy + Math.sin(angle) * radius };
  });

// Each entry returns the three things a schematic is made of: `fixtures` (a
// stage, board or bar — the thing the room points at), `tables`, and `seats`.
const LAYOUTS = {
  theatre: () => ({
    fixtures: [{ x: 70, y: 150, w: 180, h: 14, name: "Stage" }],
    tables: [],
    // A centre aisle, because a theatre row that ran unbroken across the room
    // would misrepresent how the seats are actually reachable.
    seats: grid(
      [0, 1, 2, 3, 4, 6, 7, 8, 9, 10].map((i) => 46 + i * 23),
      [34, 57, 80, 103, 126],
    ),
  }),
  classroom: () => ({
    fixtures: [{ x: 110, y: 16, w: 100, h: 8, name: "Board" }],
    tables: [34, 128, 222].flatMap((x) => [58, 98, 138].map((y) => ({ x, y, w: 64, h: 9 }))),
    seats: [34, 128, 222].flatMap((x) => [58, 98, 138].flatMap((y) => [
      { cx: x + 16, cy: y - 11 },
      { cx: x + 48, cy: y - 11 },
    ])),
  }),
  boardroom: () => ({
    fixtures: [],
    tables: [{ x: 86, y: 64, w: 148, h: 52 }],
    seats: [
      ...[0, 1, 2, 3, 4].map((i) => ({ cx: 86 + 148 * ((i + 0.5) / 5), cy: 52 })),
      ...[0, 1, 2, 3, 4].map((i) => ({ cx: 86 + 148 * ((i + 0.5) / 5), cy: 128 })),
      { cx: 74, cy: 90 },
      { cx: 246, cy: 90 },
    ],
  }),
  banquet: () => {
    const centres = [
      [76, 58],
      [160, 58],
      [244, 58],
      [76, 126],
      [160, 126],
      [244, 126],
    ];
    return {
      fixtures: [],
      tables: centres.map(([cx, cy]) => ({ cx, cy, r: 17 })),
      seats: centres.flatMap(([cx, cy]) => ring(cx, cy, 26, 6)),
    };
  },
  u_shape: () => ({
    fixtures: [],
    tables: [
      { x: 84, y: 48, w: 152, h: 12 },
      { x: 84, y: 48, w: 12, h: 88 },
      { x: 224, y: 48, w: 12, h: 88 },
    ],
    seats: [
      ...[108, 140, 172, 204].map((cx) => ({ cx, cy: 38 })),
      ...[74, 98, 122].map((cy) => ({ cx: 72, cy })),
      ...[74, 98, 122].map((cy) => ({ cx: 248, cy })),
    ],
  }),
  reception: () => ({
    fixtures: [{ x: 100, y: 150, w: 120, h: 12, name: "Bar" }],
    // Standing tables, so no seats — that absence is the point of the layout.
    tables: [
      [70, 52],
      [140, 42],
      [216, 60],
      [96, 106],
      [176, 100],
      [250, 114],
    ].map(([cx, cy]) => ({ cx, cy, r: 10 })),
    seats: [],
  }),
};

const plan = computed(() => (LAYOUTS[props.layout] ?? LAYOUTS.boardroom)());
const rectTables = computed(() => plan.value.tables.filter((t) => t.w));
const roundTables = computed(() => plan.value.tables.filter((t) => t.r));
</script>

<template>
  <svg
    :viewBox="`0 0 ${W} ${H}`"
    class="aspect-video w-full bg-canvas"
    role="img"
    preserveAspectRatio="xMidYMid meet"
  >
    <title>{{ label || layout }} layout, schematic arrangement — not this room's floor plan</title>

    <rect x="6" y="6" :width="W - 12" :height="H - 12" class="fill-none stroke-ink" stroke-width="3" />

    <rect
      v-for="fixture in plan.fixtures"
      :key="fixture.name"
      :x="fixture.x"
      :y="fixture.y"
      :width="fixture.w"
      :height="fixture.h"
      class="fill-ink"
    />

    <rect
      v-for="(table, i) in rectTables"
      :key="`t${i}`"
      :x="table.x"
      :y="table.y"
      :width="table.w"
      :height="table.h"
      class="fill-bauhaus-yellow stroke-ink"
      stroke-width="2"
    />

    <circle
      v-for="(table, i) in roundTables"
      :key="`r${i}`"
      :cx="table.cx"
      :cy="table.cy"
      :r="table.r"
      class="fill-bauhaus-yellow stroke-ink"
      stroke-width="2"
    />

    <circle
      v-for="(seat, i) in plan.seats"
      :key="`s${i}`"
      :cx="seat.cx"
      :cy="seat.cy"
      r="4.5"
      class="fill-canvas stroke-ink"
      stroke-width="2"
    />
  </svg>
</template>
