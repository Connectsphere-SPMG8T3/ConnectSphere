<script setup>
import { computed, ref } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import { ApiError, checkEquipmentAvailability, equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const activeTab = ref("availability");

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
const inventoryItems = ref([]);
const inventorySearch = ref("");
const inventoryFilter = ref("all");
const inventoryLoading = ref(false);
const inventoryError = ref("");

const statusLabel = computed(() => (results.value?.sufficient ? "SUFFICIENT" : "INSUFFICIENT"));

function inventoryStatus(item) {
  if (item.net_available === 0) return { label: "OUT OF STOCK", filter: "out-of-stock", classes: "bg-bauhaus-red text-canvas" };
  if (item.maintenance_quantity > 0) return { label: "UNDER REPAIR", filter: "maintenance", classes: "bg-orange-400 text-ink" };
  if (item.reserved_quantity > 0) return { label: "PARTIALLY RESERVED", filter: "partial", classes: "bg-bauhaus-yellow text-ink" };
  return { label: "AVAILABLE", filter: "available", classes: "bg-green-500 text-ink" };
}

const filteredInventory = computed(() => {
  const query = inventorySearch.value.trim().toLowerCase();
  return inventoryItems.value.filter((item) => {
    const status = inventoryStatus(item);
    const matchesSearch = !query || item.name.toLowerCase().includes(query);
    const matchesFilter = inventoryFilter.value === "all"
      || (inventoryFilter.value === "maintenance" && status.filter === "maintenance")
      || (inventoryFilter.value === "partial" && status.filter === "partial")
      || (inventoryFilter.value === "available" && status.filter === "available");
    return matchesSearch && matchesFilter;
  });
});

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

async function loadInventory() {
  if (inventoryLoading.value) return;
  inventoryError.value = "";
  inventoryLoading.value = true;
  try {
    inventoryItems.value = (await authStore.withSession((token) => equipmentApi.inventory(
      new Date(startAt.value).toISOString(),
      new Date(endAt.value).toISOString(),
      token,
    ))).items;
  } catch (error) {
    inventoryError.value = error instanceof ApiError
      ? error.message
      : "Unable to load the equipment inventory. Please try again.";
  } finally {
    inventoryLoading.value = false;
  }
}

function selectTab(tab) {
  activeTab.value = tab;
  if (tab === "inventory" && inventoryItems.value.length === 0) loadInventory();
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

    <nav class="mb-8 grid grid-cols-1 border-4 border-ink sm:grid-cols-2" aria-label="Technical support views">
      <button type="button" class="border-b-2 border-ink px-5 py-4 text-left text-sm font-black uppercase tracking-widest transition-colors sm:border-b-0 sm:border-r-2" :class="activeTab === 'availability' ? 'bg-bauhaus-blue text-canvas' : 'bg-canvas hover:bg-bauhaus-yellow'" :aria-selected="activeTab === 'availability'" @click="selectTab('availability')">
        Check availability
      </button>
      <button type="button" class="px-5 py-4 text-left text-sm font-black uppercase tracking-widest transition-colors" :class="activeTab === 'inventory' ? 'bg-bauhaus-blue text-canvas' : 'bg-canvas hover:bg-bauhaus-yellow'" :aria-selected="activeTab === 'inventory'" @click="selectTab('inventory')">
        Inventory &amp; status overview
      </button>
    </nav>

    <BauhausCard v-if="activeTab === 'availability'" background="white" accent="square" accent-color="bauhaus-red">
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

    <BauhausCard v-else background="white" accent="square" accent-color="bauhaus-blue">
      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Master equipment records</p>
            <h2 class="mt-2 text-2xl font-black uppercase tracking-tight">Inventory &amp; status overview</h2>
          </div>
          <button type="button" class="border-2 border-ink px-4 py-2 text-xs font-black uppercase tracking-widest hover:bg-bauhaus-yellow disabled:cursor-not-allowed disabled:opacity-50" :disabled="inventoryLoading" @click="loadInventory">
            Refresh inventory
          </button>
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_14rem]">
          <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
            Search equipment
            <input v-model="inventorySearch" type="search" placeholder="Search by name" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
          <label class="flex flex-col gap-2 text-xs font-bold uppercase tracking-widest">
            Status filter
            <select v-model="inventoryFilter" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4">
              <option value="all">All statuses</option>
              <option value="available">Fully available</option>
              <option value="partial">Partially reserved</option>
              <option value="maintenance">Under maintenance / repair</option>
            </select>
          </label>
        </div>

        <p v-if="inventoryError" class="border-2 border-bauhaus-red bg-bauhaus-red/10 p-4 text-sm font-bold text-bauhaus-red" role="alert">{{ inventoryError }}</p>
        <div v-if="inventoryLoading" class="flex items-center gap-3 border-2 border-ink bg-bauhaus-yellow p-4 text-sm font-black uppercase tracking-widest" role="status">
          <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
          Loading inventory
        </div>
        <div v-else class="overflow-x-auto border-2 border-ink">
          <table class="w-full min-w-[48rem] text-left text-sm">
            <thead class="bg-ink text-canvas">
              <tr class="text-xs uppercase tracking-widest">
                <th class="px-4 py-3">Equipment name</th>
                <th class="px-4 py-3">Total stock</th>
                <th class="px-4 py-3">Reserved</th>
                <th class="px-4 py-3">Under maintenance</th>
                <th class="px-4 py-3">Net available</th>
                <th class="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredInventory" :key="item.equipment_id" class="border-t-2 border-ink">
                <td class="px-4 py-4 font-bold">{{ item.name }}</td>
                <td class="px-4 py-4">{{ item.total_quantity }}</td>
                <td class="px-4 py-4">{{ item.reserved_quantity }}</td>
                <td class="px-4 py-4">{{ item.maintenance_quantity }}</td>
                <td class="px-4 py-4 font-black">{{ item.net_available }}</td>
                <td class="px-4 py-4"><span class="inline-block border-2 border-ink px-3 py-1 text-xs font-black tracking-wide" :class="inventoryStatus(item).classes">{{ inventoryStatus(item).label }}</span></td>
              </tr>
              <tr v-if="filteredInventory.length === 0">
                <td colspan="6" class="px-4 py-8 text-center text-sm font-bold uppercase tracking-widest">No equipment matches this filter.</td>
              </tr>
            </tbody>
          </table>
        </div>
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
