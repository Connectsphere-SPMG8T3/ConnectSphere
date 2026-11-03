<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import SectionHeading from "@/components/common/SectionHeading.vue";
import { sectionTone } from "@/components/common/sectionTone";
import VenueEditWarningModal from "@/components/venues/VenueEditWarningModal.vue";
import { venueToEditForm } from "@/features/venues/venueProfile";
import { useVenueEditStore } from "@/features/venues/venueEditStore";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS } from "@/features/venues/venueSearchStore";

const route = useRoute();
const router = useRouter();
const breadcrumbItems = computed(() => [
  { label: "Venues", to: { name: "venue-search" } },
  { label: store.venue?.name ?? "Venue", to: { name: "venue-detail", params: { id: route.params.id } } },
  { label: "Edit" },
]);
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
  <main class="py-8">
    <BauhausBreadcrumb :items="breadcrumbItems" />

    <p v-if="store.error && !store.venue" role="alert" class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4">
      {{ store.error }}
    </p>
    <p v-else-if="store.isLoading && !store.venue" class="text-sm font-medium">Loading venue…</p>

    <form v-else-if="store.venue" class="flex flex-col gap-8" @submit.prevent="save(false)">
      <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow">
        <p class="text-sm font-bold opacity-90">Edit venue</p>
        <h1 class="mt-2 text-4xl font-bold leading-tight sm:text-5xl">{{ store.venue.name }}</h1>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <SectionHeading id="details" :tone="sectionTone(0)">Details</SectionHeading>
        <p class="mb-6 mt-3 text-base font-medium text-ink/70">Who and where the venue is, and when it is open.</p>
        <div class="flex flex-col gap-6">
          <div class="grid gap-6 sm:grid-cols-2">
            <BauhausInput v-model="form.name" label="Name" required large />
            <BauhausInput v-model="form.location" label="Location" required large />
          </div>
          <div class="flex flex-wrap gap-6">
            <BauhausInput v-model="form.capacity" type="number" min="1" label="Capacity" required large class="w-full sm:w-40" />
            <BauhausInput v-model="form.opensAt" type="time" label="Opens" required large class="w-full sm:w-44" />
            <BauhausInput v-model="form.closesAt" type="time" label="Closes" required large class="w-full sm:w-44" />
          </div>
          <label class="flex flex-col gap-2">
            <span class="text-sm font-bold text-ink">Description</span>
            <textarea
              v-model="form.description"
              rows="3"
              class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"
            ></textarea>
          </label>
        </div>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <SectionHeading id="booking-defaults" :tone="sectionTone(1)">Booking defaults &amp; safety</SectionHeading>
        <p class="mb-6 mt-3 text-base font-medium text-ink/70">
          Defaults apply to new booking requests only. Existing bookings keep their own setup and turnaround times.
        </p>
        <div class="flex flex-col gap-6">
          <div class="flex flex-wrap gap-6">
            <BauhausInput v-model="form.setupMinutes" type="number" min="0" step="1" label="Default setup (minutes)" required large class="w-full sm:w-60" />
            <BauhausInput v-model="form.turnaroundMinutes" type="number" min="0" step="1" label="Default turnaround (minutes)" required large class="w-full sm:w-64" />
          </div>
          <div class="grid gap-6 md:grid-cols-2">
            <label class="flex flex-col gap-2">
              <span class="text-sm font-bold text-ink">Emergency access</span>
              <textarea v-model="form.emergencyAccess" rows="4" class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"></textarea>
            </label>
            <label class="flex flex-col gap-2">
              <span class="text-sm font-bold text-ink">Restrictions</span>
              <textarea v-model="form.restrictions" rows="4" class="border-2 border-ink bg-canvas p-3 text-base font-medium shadow-hard focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow sm:border-4"></textarea>
            </label>
          </div>
        </div>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <SectionHeading id="layouts" :tone="sectionTone(2)">Layouts</SectionHeading>
        <p class="mb-6 mt-3 text-base font-medium text-ink/70">
          Tick each layout the venue supports. Add a capacity only when it differs from the venue's.
        </p>
        <div class="flex flex-col gap-4">
          <div v-for="option in layoutOptions" :key="option.value" class="grid gap-3 sm:grid-cols-[13rem_minmax(0,1fr)] sm:items-center">
            <label class="inline-flex cursor-pointer items-center gap-3 border-2 border-ink px-4 py-3 text-sm font-bold shadow-hard" :class="form.selectedLayouts.includes(option.value) ? 'bg-bauhaus-yellow' : 'bg-canvas'">
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
              class="w-full sm:max-w-xs"
              :aria-label="`${option.label} capacity`"
              placeholder="Capacity for this layout (optional)"
            />
          </div>
        </div>
      </BauhausCard>

      <BauhausCard background="white" accent="none">
        <SectionHeading id="facilities" :tone="sectionTone(3)">Facilities &amp; access</SectionHeading>
        <p class="mb-6 mt-3 text-base font-medium text-ink/70">What the venue has, and how people can get in and around it.</p>
        <BauhausCheckboxGroup v-model="form.facilities" label="Facilities" :options="FACILITIES" large />
        <BauhausCheckboxGroup v-model="form.accessibilityFeatures" label="Accessibility" :options="ACCESSIBILITY_FEATURES" large class="mt-6" />
      </BauhausCard>

      <p v-if="saveError" role="alert" class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4">
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
