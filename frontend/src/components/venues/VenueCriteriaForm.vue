<script setup>
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

const props = defineProps({
  criteria: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    default: () => ({}),
  },
  isLoading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["submit", "reset"]);
</script>

<template>
  <form class="flex flex-col gap-6" novalidate @submit.prevent="emit('submit')">
    <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <BauhausInput v-model="props.criteria.date" label="Event date" type="date" :error="errors.date" />
      <BauhausInput v-model="props.criteria.startTime" label="Start time" type="time" :error="errors.startTime" />
      <BauhausInput v-model="props.criteria.endTime" label="End time" type="time" :error="errors.endTime" />
    </div>
    <p class="-mt-3 text-xs font-medium text-ink/70">
      Times are Singapore time. Leave all three empty to browse without checking availability.
    </p>

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <BauhausInput
        v-model="props.criteria.minCapacity"
        label="Expected attendance"
        type="number"
        placeholder="e.g. 150"
        :error="errors.minCapacity"
      />
      <BauhausInput v-model="props.criteria.location" label="Location contains" placeholder="e.g. Bukit Timah" />
      <BauhausSelect v-model="props.criteria.layout" label="Room layout" :options="LAYOUTS" placeholder="Any layout" />
    </div>

    <BauhausCheckboxGroup v-model="props.criteria.facilities" label="Required facilities" :options="FACILITIES" />
    <BauhausCheckboxGroup
      v-model="props.criteria.accessibility"
      label="Accessibility features"
      :options="ACCESSIBILITY_FEATURES"
    />

    <div class="flex flex-wrap gap-4">
      <BauhausButton type="submit" variant="primary" :disabled="isLoading">
        {{ isLoading ? "Searching…" : "Search venues" }}
      </BauhausButton>
      <BauhausButton type="button" variant="outline" :disabled="isLoading" @click="emit('reset')">Clear</BauhausButton>
    </div>
  </form>
</template>
