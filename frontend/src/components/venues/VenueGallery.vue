<script setup>
/**
 * The venue profile's carousel (SCRUM-67).
 *
 * Slides are built by `venueSlides`: real photos first, then one schematic per
 * layout the venue supports. There are no photos on the project yet (no
 * `venue_photos` table, no storage bucket — VC-R8), so in practice this shows
 * the layout schematics, which are drawn from `venue_layouts` rather than
 * being decorative filler.
 *
 * The schematics are labelled as schematics on every slide. They illustrate an
 * arrangement, not this room's geometry, and a page whose stated job is
 * letting staff verify current information must not let a generic diagram be
 * read as a survey of the actual room.
 */
import { computed, watch } from "vue";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenueLayoutDiagram from "@/components/venues/VenueLayoutDiagram.vue";
import { stepIndex } from "@/features/venues/venueProfile";

const props = defineProps({
  slides: { type: Array, default: () => [] },
  venueName: { type: String, default: "" },
  // The small version for a search result card: a fixed-size frame beside the
  // venue's details, a one-line caption, and no dots.
  compact: { type: Boolean, default: false },
});

// The slide shown. A parent can bind it (`v-model:index`) to jump to a slide, as
// the search result card does when a layout is chosen; on its own it keeps its place.
const index = defineModel("index", { type: Number, default: 0 });

// A different venue (or a shorter list after a refresh) must not leave the
// index pointing past the end, which would render a blank frame.
watch(
  () => props.slides,
  () => {
    index.value = 0;
  },
);

const count = computed(() => props.slides.length);
const current = computed(() => props.slides[index.value] ?? null);

const caption = computed(() => {
  const slide = current.value;
  if (!slide) return "";
  if (slide.kind === "photo") return slide.caption ?? "";
  const pax = slide.capacity == null ? "" : ` · ${slide.capacity} pax`;
  return `${slide.label}${pax}`;
});

const step = (delta) => {
  index.value = stepIndex(index.value, count.value, delta);
};
</script>

<template>
  <section
    v-if="count"
    class="border-2 border-ink bg-canvas"
    :class="compact ? '' : 'mb-8 lg:flex lg:flex-col'"
    role="group"
    aria-roledescription="carousel"
    :aria-label="`${venueName} gallery`"
    tabindex="0"
    @keydown.left.prevent="step(-1)"
    @keydown.right.prevent="step(1)"
  >
    <!-- A fixed, modest band rather than an aspect ratio: `aspect-video` on a
         full-width container makes the slide taller than the rest of the page
         put together on a desktop. The schematic scales within it and centres;
         a photo crops to fill. -->
    <div
      class="relative flex items-center justify-center overflow-hidden bg-canvas"
      :class="compact ? 'h-40' : 'h-44 sm:h-56 lg:h-auto lg:min-h-0 lg:flex-1'"
    >
      <img
        v-if="current.kind === 'photo'"
        :src="current.url"
        :alt="current.caption || `${venueName}, photo ${index + 1} of ${count}`"
        class="h-full w-full object-cover"
      />
      <VenueLayoutDiagram v-else :layout="current.layout" :label="current.label" />

      <button
        v-if="count > 1"
        type="button"
        class="absolute top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas text-sm font-bold hover:bg-muted active-press"
        :class="compact ? 'left-2 px-2 py-1' : 'left-3 px-3 py-2'"
        aria-label="Previous slide"
        @click="step(-1)"
      >
        ←
      </button>
      <button
        v-if="count > 1"
        type="button"
        class="absolute top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas text-sm font-bold hover:bg-muted active-press"
        :class="compact ? 'right-2 px-2 py-1' : 'right-3 px-3 py-2'"
        aria-label="Next slide"
        @click="step(1)"
      >
        →
      </button>
    </div>

    <div v-if="compact" class="border-t-2 border-ink px-3 py-2">
      <div class="flex items-baseline justify-between gap-2">
        <p class="text-xs font-bold">{{ caption }}</p>
        <p class="shrink-0 text-xs font-medium text-ink/70" aria-live="polite">{{ index + 1 }} of {{ count }}</p>
      </div>
      <p v-if="current.kind === 'layout'" class="mt-0.5 text-xs font-medium text-ink/70">
        Schematic, not this room's floor plan
      </p>
    </div>

    <div v-else class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t-2 border-ink px-4 py-3">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p class="text-sm font-bold" aria-live="polite">{{ index + 1 }} of {{ count }}</p>
        <p v-if="caption" class="text-sm font-bold">{{ caption }}</p>
        <p v-if="current.kind === 'layout'" class="text-sm font-medium text-ink/70">
          Schematic arrangement — not this room's floor plan{{
            current.usesVenueCapacity ? "; capacity is the venue figure, not measured for this layout" : ""
          }}
        </p>
      </div>

      <ul v-if="count > 1" class="flex gap-2">
        <li v-for="(slide, i) in slides" :key="slide.key">
          <button
            type="button"
            class="h-3 w-3 rounded-full border-2 border-ink active-press"
            :class="i === index ? 'bg-ink' : 'bg-canvas hover:bg-muted'"
            :aria-label="`Go to slide ${i + 1}`"
            :aria-current="i === index ? 'true' : 'false'"
            @click="index = i"
          />
        </li>
      </ul>
    </div>
  </section>

  <div
    v-else-if="compact"
    class="flex h-full min-h-40 items-center justify-center border-2 border-ink bg-canvas p-4 text-center text-xs font-bold text-ink/70"
  >
    No images on file
  </div>

  <BauhausEmptyState
    v-else
    class="mb-8"
    title="Nothing to show"
    detail="This venue has no photos on file and records no supported layouts."
  />
</template>
