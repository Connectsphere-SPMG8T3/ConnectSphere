<script setup>
import { computed, ref, watch } from "vue";
import { useRoute } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { ApiError, checkEquipmentAvailability, equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const route = useRoute();
// The tabs live in the sidebar (Nav.vue), which links here with ?tab=.
// Inventory is the main view, so it is what a tech support login lands on.
const activeTab = computed(() => (route.query.tab === "availability" ? "availability" : "inventory"));

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
// Set only once an inventory response has arrived, so a failed or pending
// load shows a dash rather than a zero the page cannot stand behind.
const inventoryLoaded = ref(false);
const maintenanceItems = ref([]);
const maintenanceLoading = ref(false);
const maintenanceError = ref("");
const statusLabel = computed(() => (results.value?.sufficient ? "SUFFICIENT" : "INSUFFICIENT"));

// Status badges use the venue-staff dashboard's vocabulary: red is a problem,
// yellow wants attention, blue is informational, and green (the one colour
// outside the primaries) means the item needs nothing from you.
const pillClasses = {
  red: "bg-bauhaus-red text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  blue: "bg-bauhaus-blue text-canvas",
  green: "bg-bauhaus-green text-canvas",
  plain: "bg-canvas text-ink",
  muted: "bg-muted text-ink/70",
};

function inventoryStatus(item) {
  if (item.net_available === 0) return { label: "OUT OF STOCK", filter: "out-of-stock", classes: pillClasses.red };
  if (item.maintenance_quantity > 0) return { label: "UNDER REPAIR", filter: "maintenance", classes: pillClasses.yellow };
  if (item.reserved_quantity > 0) return { label: "PARTIALLY RESERVED", filter: "partial", classes: pillClasses.blue };
  return { label: "AVAILABLE", filter: "available", classes: pillClasses.green };
}

const maintenanceStatusClasses = {
  SCHEDULED: pillClasses.plain,
  IN_PROGRESS: pillClasses.yellow,
};

function maintenanceStatusClass(status) {
  return maintenanceStatusClasses[status] ?? pillClasses.muted;
}

// The tile row, in the venue-staff dashboard's shape: each tile's colour is
// the badge colour for the same status in the table below.
const tiles = computed(() => {
  const show = (value) => (inventoryLoaded.value ? value : "—");
  const count = (filter) => inventoryItems.value.filter((item) => inventoryStatus(item).filter === filter).length;
  const openMaintenance = maintenanceItems.value.filter((item) => item.status !== "COMPLETED").length;
  const units = inventoryItems.value.reduce((sum, item) => sum + item.total_quantity, 0);
  return [
    {
      key: "out-of-stock",
      label: "Out of stock",
      value: show(count("out-of-stock")),
      detail: "Nothing left to reserve",
      background: "red",
      accent: "triangle",
      accentColor: "ink",
    },
    {
      key: "maintenance",
      label: "Under repair",
      value: show(count("maintenance")),
      detail: "Units held for maintenance",
      background: "yellow",
      accent: "circle",
      accentColor: "bauhaus-red",
    },
    {
      key: "scheduled",
      label: "Maintenance scheduled",
      value: show(openMaintenance),
      detail: "Scheduled or in progress",
      background: "blue",
      accent: "square",
      accentColor: "bauhaus-yellow",
    },
    {
      key: "types",
      label: "Equipment types",
      value: show(inventoryItems.value.length),
      detail: inventoryLoaded.value ? `${units} units in total` : "Loading the inventory",
      background: "white",
      accent: "none",
    },
  ];
});

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
  maintenanceError.value = "";
  inventoryLoading.value = true;
  maintenanceLoading.value = true;
  try {
    const response = await authStore.withSession(async (token) => {
      const [inventory, maintenance] = await Promise.all([
        equipmentApi.inventory(
          new Date(startAt.value).toISOString(),
          new Date(endAt.value).toISOString(),
          token,
        ),
        equipmentApi.maintenance(token),
      ]);
      return { inventory, maintenance };
    });
    inventoryItems.value = response.inventory.items;
    inventoryLoaded.value = true;
    maintenanceItems.value = response.maintenance.items;
  } catch (error) {
    const message = error instanceof ApiError
      ? error.message
      : "Unable to load equipment status. Please try again.";
    inventoryError.value = message;
    maintenanceError.value = message;
  } finally {
    inventoryLoading.value = false;
    maintenanceLoading.value = false;
  }
}

watch(
  activeTab,
  (tab) => {
    if (tab === "inventory" && inventoryItems.value.length === 0) loadInventory();
  },
  { immediate: true },
);

function formatDate(value) {
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}
</script>

<template>
  <main class="py-12">
    <template v-if="activeTab === 'inventory'">
      <p v-if="inventoryError" class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">
        {{ inventoryError }}
      </p>

      <div class="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <BauhausCard
          v-for="tile in tiles"
          :key="tile.key"
          data-testid="tile"
          :background="tile.background"
          :accent="tile.accent"
          :accent-color="tile.accentColor"
        >
          <p class="text-xs font-bold uppercase tracking-widest opacity-80">{{ tile.label }}</p>
          <p class="mt-2 text-5xl font-black tracking-tighter">{{ tile.value }}</p>
          <p class="mt-2 text-xs font-medium text-ink/60">{{ tile.detail }}</p>
        </BauhausCard>
      </div>

      <section class="mb-6" aria-labelledby="inventory-heading">
        <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="inventory-heading" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
              Inventory &amp; status
            </h2>
            <p class="text-xs font-medium text-ink/60">Every piece of equipment, with how much is reserved or in maintenance for the event window set under Availability.</p>
          </div>
          <BauhausButton type="button" variant="outline" :disabled="inventoryLoading" @click="loadInventory">
            Refresh inventory
          </BauhausButton>
        </div>

        <div class="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_14rem]">
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

        <div v-if="inventoryLoading" class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold uppercase tracking-widest text-ink/70 sm:border-4" role="status">
          <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
          Loading inventory
        </div>
        <div v-else class="overflow-x-auto border-2 border-ink bg-canvas shadow-hard sm:border-4">
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
                <td class="px-4 py-4 font-black uppercase tracking-tighter">{{ item.name }}</td>
                <td class="px-4 py-4">{{ item.total_quantity }}</td>
                <td class="px-4 py-4">{{ item.reserved_quantity }}</td>
                <td class="px-4 py-4">{{ item.maintenance_quantity }}</td>
                <td class="px-4 py-4 font-black">{{ item.net_available }}</td>
                <td class="px-4 py-4"><span class="inline-block border-2 border-ink px-3 py-1 text-[10px] font-bold uppercase tracking-widest" :class="inventoryStatus(item).classes">{{ inventoryStatus(item).label }}</span></td>
              </tr>
              <tr v-if="filteredInventory.length === 0">
                <td colspan="6" class="px-4 py-8 text-center text-sm font-bold uppercase tracking-widest text-ink/60">No equipment matches this filter.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section aria-labelledby="incoming-requests-heading">
          <h2 id="incoming-requests-heading" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
            Active requests
          </h2>
          <p class="mb-4 text-xs font-medium text-ink/60">Equipment requests waiting on your decision.</p>
          <BauhausEmptyState
            title="No request workflow yet"
            detail="Equipment requests appear here once organisers can raise them and tech support can reserve or reject them (SCRUM-24)."
          />
        </section>

        <section aria-labelledby="maintenance-heading">
          <h2 id="maintenance-heading" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
            Scheduled maintenance
          </h2>
          <p class="mb-4 text-xs font-medium text-ink/60">Oldest first, from the live equipment records.</p>
          <div v-if="maintenanceLoading" class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold uppercase tracking-widest text-ink/70 sm:border-4" role="status">
            <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
            Loading maintenance
          </div>
          <ul v-else-if="maintenanceItems.length" class="flex max-h-[28rem] flex-col gap-3 overflow-y-auto pb-1 pr-1">
            <li v-for="item in maintenanceItems" :key="item.maintenance_id" class="flex flex-col gap-2 border-2 border-ink bg-canvas p-4 shadow-hard sm:border-4">
              <div class="flex flex-wrap items-baseline justify-between gap-2">
                <span class="text-base font-black uppercase leading-tight tracking-tighter">{{ item.equipment_name }}</span>
                <span class="shrink-0 border-2 border-ink px-3 py-1 text-[10px] font-bold uppercase tracking-widest" :class="maintenanceStatusClass(item.status)">{{ item.status.replace("_", " ") }}</span>
              </div>
              <span class="text-sm font-medium text-ink/75">{{ item.reason || "No reason provided" }}</span>
              <span class="text-xs font-bold uppercase tracking-widest text-ink/55">{{ formatDate(item.start_at) }} – {{ formatDate(item.end_at) }}</span>
            </li>
          </ul>
          <BauhausEmptyState
            v-else
            title="No maintenance scheduled"
            :detail="maintenanceError ? 'The maintenance records could not be loaded.' : 'No equipment is booked for maintenance.'"
          />
        </section>
      </div>
    </template>

    <template v-else>
      <section class="mb-6" aria-labelledby="availability-heading">
        <h2 id="availability-heading" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
          Event time window
        </h2>
        <p class="mb-4 text-xs font-medium text-ink/60">
          Check functional equipment against existing reservations and unavailable stock for a specific event window.
        </p>

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
      </section>

      <section class="mb-6" aria-labelledby="requested-heading">
        <div class="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 id="requested-heading" class="mb-1 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
              Requested equipment
            </h2>
            <p class="text-xs font-medium text-ink/60">Add a row for each piece of equipment the event needs.</p>
          </div>
          <BauhausButton type="button" variant="outline" @click="addItem">Add item</BauhausButton>
        </div>

        <ul class="flex flex-col gap-3">
          <li v-for="(item, index) in items" :key="index" class="grid grid-cols-1 gap-4 border-2 border-ink bg-canvas p-4 shadow-hard sm:grid-cols-[1fr_1fr_7rem_auto] sm:items-end sm:border-4">
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
            <button type="button" class="border-2 border-ink px-3 py-3 text-xs font-bold uppercase tracking-widest active-press hover:bg-bauhaus-red hover:text-canvas disabled:cursor-not-allowed disabled:opacity-40" :disabled="items.length === 1" @click="removeItem(index)">
              Remove
            </button>
          </li>
        </ul>
      </section>

      <div class="flex flex-col gap-4">
        <p v-if="validationMessage" class="border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">{{ validationMessage }}</p>
        <p v-if="errorMessage" class="border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">{{ errorMessage }}</p>

        <BauhausButton type="button" variant="secondary" full-width :disabled="isLoading" @click="checkAvailability">
          <span v-if="isLoading" class="h-4 w-4 animate-spin rounded-full border-2 border-canvas border-t-transparent" aria-hidden="true"></span>
          {{ isLoading ? "Checking availability" : "Check real-time availability" }}
        </BauhausButton>
      </div>

      <section v-if="results" class="mt-10" aria-labelledby="result-heading">
        <div class="mb-4 flex flex-wrap items-end justify-between gap-4">
          <h2 id="result-heading" class="text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
            Equipment status
          </h2>
          <span class="border-2 border-ink px-4 py-2 text-xs font-bold uppercase tracking-widest" :class="results.sufficient ? pillClasses.green : pillClasses.red">{{ statusLabel }}</span>
        </div>

        <div class="overflow-x-auto border-2 border-ink bg-canvas shadow-hard sm:border-4">
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
                <td class="px-4 py-4 font-black uppercase tracking-tighter">{{ item.name }}</td>
                <td class="px-4 py-4">{{ item.quantity_needed }}</td>
                <td class="px-4 py-4">{{ item.quantity_available }}</td>
                <td class="px-4 py-4 font-black uppercase" :class="item.sufficient ? 'text-bauhaus-green' : 'text-bauhaus-red'">{{ item.sufficient ? "Sufficient" : "Insufficient" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>
