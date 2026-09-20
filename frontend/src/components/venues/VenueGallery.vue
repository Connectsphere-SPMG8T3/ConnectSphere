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
import { computed, ref, watch } from "vue";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import VenueLayoutDiagram from "@/components/venues/VenueLayoutDiagram.vue";
import { stepIndex } from "@/features/venues/venueProfile";

const props = defineProps({
  slides: { type: Array, default: () => [] },
  venueName: { type: String, default: "" },
});

const index = ref(0);

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
    class="mb-8 border-2 border-ink bg-canvas shadow-hard sm:border-4"
    role="group"
    aria-roledescription="carousel"
    :aria-label="`${venueName} gallery`"
    tabindex="0"
    @keydown.left.prevent="step(-1)"
    @keydown.right.prevent="step(1)"
  >
    <div class="relative">
      <img
        v-if="current.kind === 'photo'"
        :src="current.url"
        :alt="current.caption || `${venueName}, photo ${index + 1} of ${count}`"
        class="aspect-video w-full object-cover"
      />
      <VenueLayoutDiagram v-else :layout="current.layout" :label="current.label" />

      <button
        v-if="count > 1"
        type="button"
        class="absolute left-3 top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas px-3 py-2 text-sm font-black active-press"
        aria-label="Previous slide"
        @click="step(-1)"
      >
        ←
      </button>
      <button
        v-if="count > 1"
        type="button"
        class="absolute right-3 top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas px-3 py-2 text-sm font-black active-press"
        aria-label="Next slide"
        @click="step(1)"
      >
        →
      </button>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t-2 border-ink px-4 py-3 sm:border-t-4">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p class="text-xs font-bold uppercase tracking-widest" aria-live="polite">{{ index + 1 }} of {{ count }}</p>
        <p v-if="caption" class="text-sm font-bold uppercase tracking-wide">{{ caption }}</p>
        <p v-if="current.kind === 'layout'" class="text-xs font-medium text-ink/60">
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
            :class="i === index ? 'bg-ink' : 'bg-canvas'"
            :aria-label="`Go to slide ${i + 1}`"
            :aria-current="i === index ? 'true' : 'false'"
            @click="index = i"
          />
        </li>
      </ul>
    </div>
  </section>

  <BauhausEmptyState
    v-else
    class="mb-8"
    title="Nothing to show"
    detail="This venue has no photos on file and records no supported layouts."
  />
</template>
