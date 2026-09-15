<script setup>
import { onMounted } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import VenueCriteriaForm from "@/components/venues/VenueCriteriaForm.vue";
import VenueResultCard from "@/components/venues/VenueResultCard.vue";
import { useVenuesStore } from "@/stores/venues";

const venuesStore = useVenuesStore();

// First visit lists the whole catalogue; coming back from a detail page keeps
// the previous search (the store outlives the view).
onMounted(() => {
  if (!venuesStore.hasSearched) venuesStore.search();
});

function handleReset() {
  venuesStore.resetCriteria();
  venuesStore.search();
}
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Venue catalogue</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">Find a venue</h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Enter the event's requirements. Every filter you set is strict; venues that miss one are listed separately with
        the reason.
      </p>
    </BauhausCard>

    <BauhausCard background="white" accent="none" class="mb-10">
      <VenueCriteriaForm
        :criteria="venuesStore.criteria"
        :errors="venuesStore.fieldErrors"
        :is-loading="venuesStore.isLoading"
        @submit="venuesStore.search()"
        @reset="handleReset"
      />
    </BauhausCard>

    <p
      v-if="venuesStore.error"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ venuesStore.error }}
    </p>

    <section v-if="venuesStore.hasSearched" aria-live="polite">
      <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-2xl font-black uppercase tracking-tight">
          {{ venuesStore.includedCount }} matching {{ venuesStore.includedCount === 1 ? "venue" : "venues" }}
          <span v-if="!venuesStore.hasPeriod" class="block text-xs font-bold uppercase tracking-widest text-ink/70">
            Add a date and time to check availability
          </span>
        </h2>
        <BauhausButton
          v-if="venuesStore.excludedCount > 0"
          variant="outline"
          @click="venuesStore.showExcluded = !venuesStore.showExcluded"
        >
          {{ venuesStore.showExcluded ? "Hide" : "Show" }} {{ venuesStore.excludedCount }} excluded
        </BauhausButton>
      </div>

      <p v-if="venuesStore.includedCount === 0" class="mb-8 text-sm font-medium">
        No venue meets every requirement. Show the excluded venues to see what each one is missing.
      </p>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <VenueResultCard v-for="result in venuesStore.includedResults" :key="result.venue.id" :result="result" />
      </div>

      <template v-if="venuesStore.showExcluded && venuesStore.excludedResults.length">
        <h2 class="mb-6 mt-12 text-2xl font-black uppercase tracking-tight">Excluded venues</h2>
        <div class="grid grid-cols-1 gap-6 opacity-90 lg:grid-cols-2">
          <VenueResultCard v-for="result in venuesStore.excludedResults" :key="result.venue.id" :result="result" />
        </div>
      </template>
    </section>
  </main>
</template>
