<script setup>
/**
 * The venue profile's photo slideshow (SCRUM-67).
 *
 * `photos` is always empty today: there is no `venue_photos` table and no
 * storage bucket, so `VenueDetail.photos` comes back `[]`. The component is
 * built against the real shape and leads with an honest empty state rather
 * than stock imagery — this page exists so staff can verify *current*
 * information, and invented photos would undermine exactly that
 * (`frontend/AGENTS.md`, "Empty states, not fake data").
 */
import { computed, ref, watch } from "vue";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { stepIndex } from "@/features/venues/venueProfile";

const props = defineProps({
  photos: { type: Array, default: () => [] },
  venueName: { type: String, default: "" },
});

const index = ref(0);

// A different venue (or a shorter list after a refresh) must not leave the
// index pointing past the end, which would render a blank frame.
watch(
  () => props.photos,
  () => {
    index.value = 0;
  },
);

const count = computed(() => props.photos.length);
const current = computed(() => props.photos[index.value] ?? null);

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
    :aria-label="`Photos of ${venueName}`"
    tabindex="0"
    @keydown.left.prevent="step(-1)"
    @keydown.right.prevent="step(1)"
  >
    <div class="relative">
      <img
        :src="current.url"
        :alt="current.caption || `${venueName}, photo ${index + 1} of ${count}`"
        class="aspect-video w-full object-cover"
      />

      <button
        v-if="count > 1"
        type="button"
        class="absolute left-3 top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas px-3 py-2 text-sm font-black active-press"
        aria-label="Previous photo"
        @click="step(-1)"
      >
        ←
      </button>
      <button
        v-if="count > 1"
        type="button"
        class="absolute right-3 top-1/2 -translate-y-1/2 border-2 border-ink bg-canvas px-3 py-2 text-sm font-black active-press"
        aria-label="Next photo"
        @click="step(1)"
      >
        →
      </button>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3 border-t-2 border-ink px-4 py-3 sm:border-t-4">
      <p class="text-xs font-bold uppercase tracking-widest" aria-live="polite">
        Photo {{ index + 1 }} of {{ count }}
      </p>
      <p v-if="current.caption" class="text-sm font-medium text-ink/70">{{ current.caption }}</p>
      <ul v-if="count > 1" class="flex gap-2">
        <li v-for="(photo, i) in photos" :key="photo.url">
          <button
            type="button"
            class="h-3 w-3 rounded-full border-2 border-ink active-press"
            :class="i === index ? 'bg-ink' : 'bg-canvas'"
            :aria-label="`Go to photo ${i + 1}`"
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
    title="No photos yet"
    detail="This venue has no photos on file. Adding them needs the venue photo library, which is not built."
  />
</template>
