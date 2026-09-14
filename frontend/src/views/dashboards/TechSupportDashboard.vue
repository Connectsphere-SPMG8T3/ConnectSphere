<script setup>
import { computed, ref } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import { ApiError, checkEquipmentAvailability } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

function localDateTime(hour) {
  const date = new Date();
  date.setHours(hour, 0, 0, 0);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

const startAt = ref(localDateTime(9));
const endAt = ref(localDateTime(17));
const equipmentCatalog = [
  { id: "b0000000-0000-4000-8000-000000000001", name: "4K Projector", type: "Projector" },
  { id: "b0000000-0000-4000-8000-000000000002", name: "Wireless Mics", type: "Microphone" },
  { id: "b0000000-0000-4000-8000-000000000003", name: "PA Systems", type: "Audio" },
  { id: "b0000000-0000-4000-8000-000000000004", name: "Stage Lighting", type: "Lighting" },
  { id: "b0000000-0000-4000-8000-000000000005", name: "HDMI Switchers", type: "Video" },
];
const items = ref([{ equipmentId: equipmentCatalog[0].id, quantityNeeded: 1 }]);
const results = ref(null);
const isLoading = ref(false);
const errorMessage = ref("");
const validationMessage = ref("");

const statusLabel = computed(() => (results.value?.sufficient ? "SUFFICIENT" : "INSUFFICIENT"));

function addItem() {
  items.value.push({ equipmentId: equipmentCatalog[0].id, quantityNeeded: 1 });
}

function removeItem(index) {
  if (items.value.length === 1) return;
  items.value.splice(index, 1);
}

function validateForm() {
  validationMessage.value = "";
  if (!startAt.value || !endAt.value || new Date(endAt.value) <= new Date(startAt.value)) {
    validationMessage.value = "End time must be later than the start time.";
    return false;
  }
  if (items.value.some((item) => !equipmentCatalog.some((equipment) => equipment.id === item.equipmentId) || !Number.isInteger(Number(item.quantityNeeded)) || Number(item.quantityNeeded) < 1)) {
    validationMessage.value = "Choose equipment and enter a quantity of at least 1 for every item.";
    return false;
  }
  return true;
}

async function checkAvailability() {
  results.value = null;
  errorMessage.value = "";
  if (!validateForm()) return;

  isLoading.value = true;
  try {
    const payload = {
      start_at: new Date(startAt.value).toISOString(),
      end_at: new Date(endAt.value).toISOString(),
      items: items.value.map((item) => ({
        equipment_id: item.equipmentId,
        quantity_needed: Number(item.quantityNeeded),
      })),
    };
    results.value = await authStore.withSession((token) => checkEquipmentAvailability(payload, token));
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) {
      errorMessage.value = "Access denied. Only Technical Support Staff can check equipment availability.";
    } else if (error instanceof ApiError) {
      errorMessage.value = error.message;
    } else {
      errorMessage.value = "Unable to check equipment availability. Please try again.";
    }
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Technical Support Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Check functional equipment against existing reservations and unavailable stock for a specific event window.
      </p>
    </BauhausCard>

    <BauhausCard background="white" accent="square" accent-color="bauhaus-red">
      <div class="flex flex-col gap-6">
        <div>
          <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Availability check</p>
          <h2 class="mt-2 text-2xl font-black uppercase tracking-tight">Event time window</h2>
        </div>

        <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
            Start date and time
            <input v-model="startAt" type="datetime-local" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
          <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
            End date and time
            <input v-model="endAt" type="datetime-local" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
        </div>

        <div class="flex items-end justify-between gap-4 border-t-2 border-ink pt-6">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Requested equipment</p>
            <h2 class="mt-2 text-2xl font-black uppercase tracking-tight">Inventory list</h2>
          </div>
          <BauhausButton type="button" variant="outline" @click="addItem">Add item</BauhausButton>
        </div>

        <div class="flex flex-col gap-4">
          <div v-for="(item, index) in items" :key="index" class="grid grid-cols-1 gap-4 border-2 border-ink p-4 sm:grid-cols-[1fr_1fr_7rem_auto] sm:items-end">
            <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
              Equipment ID / type
              <select v-model="item.equipmentId" class="border-2 border-ink bg-canvas px-3 py-3 text-sm font-medium outline-none focus:bg-bauhaus-yellow/20">
                <option v-for="equipment in equipmentCatalog" :key="equipment.id" :value="equipment.id">
                  {{ equipment.name }} · {{ equipment.type }}
                </option>
              </select>
            </label>
            <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
              Needed
              <input v-model.number="item.quantityNeeded" type="number" min="1" class="border-2 border-ink bg-canvas px-3 py-3 text-sm font-medium outline-none focus:bg-bauhaus-yellow/20" />
            </label>
            <button type="button" class="border-2 border-ink px-3 py-3 text-xs font-bold uppercase tracking-widest hover:bg-bauhaus-red hover:text-canvas disabled:cursor-not-allowed disabled:opacity-40" :disabled="items.length === 1" @click="removeItem(index)">
              Remove
            </button>
          </div>
        </div>

        <p v-if="validationMessage" class="border-2 border-bauhaus-red bg-bauhaus-red/10 p-4 text-sm font-bold text-bauhaus-red" role="alert">{{ validationMessage }}</p>
        <p v-if="errorMessage" class="border-2 border-bauhaus-red bg-bauhaus-red/10 p-4 text-sm font-bold text-bauhaus-red" role="alert">{{ errorMessage }}</p>

        <BauhausButton type="button" variant="secondary" full-width :disabled="isLoading" @click="checkAvailability">
          <span v-if="isLoading" class="h-4 w-4 animate-spin rounded-full border-2 border-canvas border-t-transparent" aria-hidden="true"></span>
          {{ isLoading ? "Checking availability" : "Check real-time availability" }}
        </BauhausButton>
      </div>
    </BauhausCard>

    <BauhausCard v-if="results" :background="results.sufficient ? 'yellow' : 'white'" accent="triangle" :accent-color="results.sufficient ? 'ink' : 'bauhaus-red'" class="mt-8">
      <div class="flex flex-col gap-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Live result</p>
            <h2 class="mt-2 text-2xl font-black uppercase tracking-tight">Equipment status</h2>
          </div>
          <span class="border-2 border-ink px-4 py-2 text-sm font-black tracking-widest" :class="results.sufficient ? 'bg-green-500 text-ink' : 'bg-bauhaus-red text-canvas'">{{ statusLabel }}</span>
        </div>

        <div class="overflow-x-auto border-2 border-ink">
          <table class="w-full min-w-[34rem] text-left text-sm">
            <thead class="bg-ink text-canvas">
              <tr class="text-xs uppercase tracking-widest">
                <th class="px-4 py-3">Equipment name</th>
                <th class="px-4 py-3">Needed</th>
                <th class="px-4 py-3">Available</th>
                <th class="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in results.items" :key="item.equipment_id" class="border-t-2 border-ink">
                <td class="px-4 py-4 font-bold">{{ item.name }}</td>
                <td class="px-4 py-4">{{ item.quantity_needed }}</td>
                <td class="px-4 py-4">{{ item.quantity_available }}</td>
                <td class="px-4 py-4 font-black uppercase" :class="item.sufficient ? 'text-green-700' : 'text-bauhaus-red'">{{ item.sufficient ? "Sufficient" : "Insufficient" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </BauhausCard>
  </main>
</template>
