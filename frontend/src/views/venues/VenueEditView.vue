<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import VenueEditWarningModal from "@/components/venues/VenueEditWarningModal.vue";
import { venueToEditForm } from "@/features/venues/venueProfile";
import { useVenueEditStore } from "@/features/venues/venueEditStore";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

const route = useRoute();
const router = useRouter();
const store = useVenueEditStore();

const form = reactive(venueToEditForm(null));
const showWarnings = ref(false);
const saveError = ref(null);

async function load() {
  saveError.value = null;
  await store.load(route.params.id);
  Object.assign(form, venueToEditForm(store.venue));
}

onMounted(load);
watch(() => route.params.id, load);

function toggleLayout(layout, checked) {
  form.selectedLayouts = checked ? [...form.selectedLayouts, layout] : form.selectedLayouts.filter((l) => l !== layout);
}

async function save(confirm = false) {
  saveError.value = null;
  try {
    const saved = await store.submit(form, { confirm });
    if (saved) {
      router.push({ name: "venue-detail", params: { id: route.params.id } });
    } else {
      showWarnings.value = true;
    }
  } catch (error) {
    saveError.value = error.message;
    showWarnings.value = false;
  }
}

function confirmSave() {
  save(true);
}

function cancelWarning() {
  showWarnings.value = false;
}

const layoutOptions = computed(() => LAYOUTS);
</script>

<template>
  <main class="py-12">
    <RouterLink
      :to="{ name: 'venue-detail', params: { id: route.params.id } }"
      class="mb-8 inline-block text-xs font-bold uppercase tracking-widest underline decoration-2 underline-offset-4"
    >
      ← Back to venue profile
    </RouterLink>

    <p v-if="store.error && !store.venue" role="alert" class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4">
      {{ store.error }}
    </p>
    <p v-else-if="store.isLoading && !store.venue" class="text-sm font-medium">Loading venue…</p>

    <form v-else-if="store.venue" class="flex flex-col gap-8" @submit.prevent="save(false)">
      <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">Edit venue</p>
        <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ store.venue.name }}</h1>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Details</h2>
        <div class="grid gap-4 sm:grid-cols-2">
          <BauhausInput v-model="form.name" label="Name" required />
          <BauhausInput v-model="form.location" label="Location" required />
          <BauhausInput v-model="form.capacity" type="number" min="1" label="Capacity" required />
          <BauhausInput v-model="form.opensAt" type="time" label="Opens" required />
          <BauhausInput v-model="form.closesAt" type="time" label="Closes" required />
        </div>
        <label class="mt-4 flex flex-col gap-2">
          <span class="text-xs font-bold uppercase tracking-widest text-ink">Description</span>
          <textarea
            v-model="form.description"
            rows="3"
            class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"
          ></textarea>
        </label>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Booking defaults &amp; safety</h2>
        <p class="mb-4 text-sm font-medium">Defaults apply to new booking requests only. Existing bookings keep their own setup and turnaround times.</p>
        <div class="grid gap-4 sm:grid-cols-2">
          <BauhausInput v-model="form.setupMinutes" type="number" min="0" step="1" label="Default setup (minutes)" required />
          <BauhausInput v-model="form.turnaroundMinutes" type="number" min="0" step="1" label="Default turnaround (minutes)" required />
        </div>
        <label class="mt-4 flex flex-col gap-2">
          <span class="text-xs font-bold uppercase tracking-widest text-ink">Emergency access</span>
          <textarea v-model="form.emergencyAccess" rows="3" class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"></textarea>
        </label>
        <label class="mt-4 flex flex-col gap-2">
          <span class="text-xs font-bold uppercase tracking-widest text-ink">Restrictions</span>
          <textarea v-model="form.restrictions" rows="3" class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"></textarea>
        </label>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Layouts</h2>
        <div class="flex flex-col gap-3">
          <div v-for="option in layoutOptions" :key="option.value" class="flex flex-wrap items-center gap-3">
            <label class="inline-flex cursor-pointer items-center gap-2 border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-wide shadow-hard" :class="form.selectedLayouts.includes(option.value) ? 'bg-bauhaus-yellow' : 'bg-canvas'">
              <input
                type="checkbox"
                class="h-4 w-4 accent-bauhaus-red"
                :checked="form.selectedLayouts.includes(option.value)"
                @change="toggleLayout(option.value, $event.target.checked)"
              />
              {{ option.label }}
            </label>
            <BauhausInput
              v-if="form.selectedLayouts.includes(option.value)"
              v-model="form.layoutCapacities[option.value]"
              type="number"
              min="1"
              compact
              :aria-label="`${option.label} capacity`"
              placeholder="Capacity for this layout (optional)"
            />
          </div>
        </div>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <h2 class="mb-4 text-lg font-black uppercase tracking-tight">Facilities &amp; access</h2>
        <BauhausCheckboxGroup v-model="form.facilities" label="Facilities" :options="FACILITIES" />
        <BauhausCheckboxGroup v-model="form.accessibilityFeatures" label="Accessibility" :options="ACCESSIBILITY_FEATURES" class="mt-6" />
      </BauhausCard>

      <p v-if="saveError" role="alert" class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4">
        {{ saveError }}
      </p>

      <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <BauhausButton type="button" variant="outline" @click="router.push({ name: 'venue-detail', params: { id: route.params.id } })">
          Cancel
        </BauhausButton>
        <BauhausButton type="submit" variant="primary" :disabled="store.isSaving">Save changes</BauhausButton>
      </div>
    </form>

    <VenueEditWarningModal
      :open="showWarnings"
      :warnings="store.warnings"
      :busy="store.isSaving"
      @confirm="confirmSave"
      @cancel="cancelWarning"
    />
  </main>
</template>
