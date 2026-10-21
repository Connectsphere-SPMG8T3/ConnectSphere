<script setup>
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { useEquipmentQueueStore } from "@/features/equipment/equipmentQueueStore";
import {
  defaultInventoryWindow,
  describeInventoryWindow,
  inventoryWindowError,
} from "@/features/equipment/inventoryWindow";
import { ApiError, equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const route = useRoute();
// SCRUM-24: the lines waiting on tech support, counted on the first tile.
const queue = useEquipmentQueueStore();
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
// D47: the check offers the live catalogue (GET /equipment/catalogue), loaded
// when the availability view first opens, rather than a fixed list.
const catalogue = ref([]);
const catalogueLoading = ref(false);
const catalogueError = ref("");
const items = ref([{ equipmentId: null, quantityNeeded: 1 }]);
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
// D46: the table counts one window, its own rather than the availability
// check's, and says which. shownWindow is the window the rows were loaded for.
const initialWindow = defaultInventoryWindow();
const inventoryStartAt = ref(initialWindow.startAt);
const inventoryEndAt = ref(initialWindow.endAt);
const shownWindow = ref(null);
const inventoryWindowMessage = computed(() => inventoryWindowError(inventoryStartAt.value, inventoryEndAt.value));
const inventoryWindowText = computed(() => {
  const window = shownWindow.value ?? { startAt: inventoryStartAt.value, endAt: inventoryEndAt.value };
  const label = describeInventoryWindow(window.startAt, window.endAt);
  return shownWindow.value ? `Showing stock for ${label}` : `Loading stock for ${label}`;
});
// Only the latest load may fill the table, so changing the window quickly
// can't leave an earlier window's numbers under the new label.
let latestInventoryLoad = 0;
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
      // SCRUM-24: as venue staff's "Pending requests" tile, it opens the full
      // list. Out-of-stock items are still badged and filterable in the table.
      key: "requests",
      label: "Active requests",
      value: queue.isLoaded ? queue.waitingCount : "—",
      detail: "Awaiting your decision",
      to: { name: "dashboard-tech-support-requests" },
      background: "yellow",
      accent: "circle",
      accentColor: "bauhaus-red",
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
      || (inventoryFilter.value === "out-of-stock" && status.filter === "out-of-stock")
      || (inventoryFilter.value === "maintenance" && status.filter === "maintenance")
      || (inventoryFilter.value === "partial" && status.filter === "partial")
      || (inventoryFilter.value === "available" && status.filter === "available");
    return matchesSearch && matchesFilter;
  });
});

const firstItemId = () => catalogue.value[0]?.equipment_id ?? null;

async function loadCatalogue() {
  catalogueLoading.value = true;
  catalogueError.value = "";
  try {
    const response = await authStore.withSession((token) => equipmentApi.catalogue(token));
    catalogue.value = response.items;
    for (const item of items.value) if (!item.equipmentId) item.equipmentId = firstItemId();
  } catch {
    catalogueError.value = "The equipment catalogue could not be loaded, so availability can't be checked. Refresh the page to try again.";
  } finally {
    catalogueLoading.value = false;
  }
}

function addItem() {
  items.value.push({ equipmentId: firstItemId(), quantityNeeded: 1 });
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
  if (items.value.some((item) => !catalogue.value.some((equipment) => equipment.equipment_id === item.equipmentId) || !Number.isInteger(Number(item.quantityNeeded)) || Number(item.quantityNeeded) < 1)) {
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
    results.value = await authStore.withSession((token) => equipmentApi.checkEquipmentAvailability(payload, token));
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
  if (inventoryWindowMessage.value) return;
  const window = { startAt: inventoryStartAt.value, endAt: inventoryEndAt.value };
  const load = ++latestInventoryLoad;
  inventoryError.value = "";
  maintenanceError.value = "";
  inventoryLoading.value = true;
  maintenanceLoading.value = true;
  try {
    const response = await authStore.withSession(async (token) => {
      const [inventory, maintenance] = await Promise.all([
        equipmentApi.inventory(
          new Date(window.startAt).toISOString(),
          new Date(window.endAt).toISOString(),
          token,
        ),
        equipmentApi.maintenance(token),
      ]);
      return { inventory, maintenance };
    });
    if (load !== latestInventoryLoad) return;
    inventoryItems.value = response.inventory.items;
    inventoryLoaded.value = true;
    shownWindow.value = window;
    maintenanceItems.value = response.maintenance.items;
  } catch (error) {
    if (load !== latestInventoryLoad) return;
    const message = error instanceof ApiError
      ? error.message
      : "Unable to load equipment status. Please try again.";
    inventoryError.value = message;
    maintenanceError.value = message;
  } finally {
    if (load === latestInventoryLoad) {
      inventoryLoading.value = false;
      maintenanceLoading.value = false;
    }
  }
}

watch([inventoryStartAt, inventoryEndAt], () => loadInventory());

watch(
  activeTab,
  (tab) => {
    if (tab === "inventory" && inventoryItems.value.length === 0) loadInventory();
    if (tab === "inventory" && !queue.isLoaded && !queue.isLoading) queue.load();
    if (tab === "availability" && !catalogue.value.length && !catalogueLoading.value) loadCatalogue();
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

      <div class="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
        <!-- The one tile that leads anywhere is a link, with the same hover cue
             as venue staff's Pending requests tile. -->
        <component
          :is="tile.to ? RouterLink : 'div'"
          v-for="tile in tiles"
          :key="tile.key"
          :to="tile.to"
          data-testid="tile"
          class="block"
          :class="tile.to ? 'group transition-shadow hover:shadow-hard focus-visible:shadow-hard active-press' : ''"
        >
          <BauhausSummaryCard
            :label="tile.label"
            :value="tile.value"
            :background="tile.background"
            :accent="tile.accent"
            :accent-color="tile.accentColor"
          >
            <template #detail>
              {{ tile.detail }}
              <span
                v-if="tile.to"
                class="font-bold text-ink opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
              >
                See the list →
              </span>
            </template>
          </BauhausSummaryCard>
        </component>
      </div>

      <section class="mb-6" aria-labelledby="inventory-heading">
        <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 id="inventory-heading" class="mb-1 text-2xl font-bold leading-tight sm:text-3xl">
              Inventory &amp; status
            </h2>
            <p class="text-xs font-medium text-ink/60">Every piece of equipment, with the most reserved or in maintenance at any one moment in the window below.</p>
          </div>
          <BauhausButton type="button" variant="outline" :disabled="inventoryLoading" @click="loadInventory">
            Refresh inventory
          </BauhausButton>
        </div>

        <div class="mb-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label class="flex flex-col gap-2 text-xs font-bold">
            Window start
            <input v-model="inventoryStartAt" type="datetime-local" :aria-invalid="inventoryWindowMessage ? 'true' : undefined" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
          <label class="flex flex-col gap-2 text-xs font-bold">
            Window end
            <input v-model="inventoryEndAt" type="datetime-local" :aria-invalid="inventoryWindowMessage ? 'true' : undefined" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
        </div>
        <p v-if="inventoryWindowMessage" data-testid="inventory-window-error" role="alert" class="mb-2 text-sm font-bold text-bauhaus-red">
          {{ inventoryWindowMessage }}
        </p>
        <p data-testid="inventory-window" class="mb-4 text-sm font-bold" aria-live="polite">{{ inventoryWindowText }}</p>

        <div class="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_14rem]">
          <label class="flex flex-col gap-2 text-xs font-bold">
            Search equipment
            <input v-model="inventorySearch" type="search" placeholder="Search by name" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
          <label class="flex flex-col gap-2 text-xs font-bold">
            Status filter
            <select v-model="inventoryFilter" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4">
              <option value="all">All statuses</option>
              <option value="out-of-stock">Out of stock</option>
              <option value="available">Fully available</option>
              <option value="partial">Partially reserved</option>
              <option value="maintenance">Under maintenance / repair</option>
            </select>
          </label>
        </div>

        <div v-if="inventoryLoading" class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold text-ink/70 sm:border-4" role="status">
          <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
          Loading inventory
        </div>
        <div v-else class="overflow-x-auto border-2 border-ink bg-canvas shadow-hard sm:border-4">
          <table class="w-full min-w-[48rem] text-left text-sm">
            <thead class="bg-ink text-canvas">
              <tr class="text-xs">
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
                <td class="px-4 py-4 font-bold">{{ item.net_available }}</td>
                <td class="px-4 py-4"><span class="inline-block border-2 border-ink px-3 py-1 text-xs font-bold" :class="inventoryStatus(item).classes">{{ inventoryStatus(item).label }}</span></td>
              </tr>
              <tr v-if="filteredInventory.length === 0">
                <td colspan="6" class="px-4 py-8 text-center text-sm font-bold text-ink/60">No equipment matches this filter.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid grid-cols-1 gap-6">
        <section aria-labelledby="maintenance-heading">
          <h2 id="maintenance-heading" class="mb-1 text-2xl font-bold leading-tight sm:text-3xl">
            Scheduled maintenance
          </h2>
          <p class="mb-4 text-xs font-medium text-ink/60">Oldest first, from the live equipment records.</p>
          <div v-if="maintenanceLoading" class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold text-ink/70 sm:border-4" role="status">
            <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
            Loading maintenance
          </div>
          <ul v-else-if="maintenanceItems.length" class="flex max-h-[28rem] flex-col gap-3 overflow-y-auto pb-1 pr-1">
            <li v-for="item in maintenanceItems" :key="item.maintenance_id" class="flex flex-col gap-2 border-2 border-ink bg-canvas p-4 shadow-hard sm:border-4">
              <div class="flex flex-wrap items-baseline justify-between gap-2">
                <span class="text-base font-bold leading-tight">{{ item.equipment_name }}</span>
                <span class="shrink-0 border-2 border-ink px-3 py-1 text-xs font-bold" :class="maintenanceStatusClass(item.status)">{{ item.status.replace("_", " ") }}</span>
              </div>
              <span class="text-sm font-medium text-ink/75">{{ item.reason || "No reason provided" }}</span>
              <span class="text-xs font-bold text-ink/55">{{ formatDate(item.start_at) }} – {{ formatDate(item.end_at) }}</span>
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
        <h2 id="availability-heading" class="mb-1 text-2xl font-bold leading-tight sm:text-3xl">
          Event time window
        </h2>
        <p class="mb-4 text-xs font-medium text-ink/60">
          Check functional equipment against existing reservations and unavailable stock for a specific event window.
        </p>

        <div class="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <label class="flex flex-col gap-2 text-xs font-bold">
            Start date and time
            <input v-model="startAt" type="datetime-local" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
          <label class="flex flex-col gap-2 text-xs font-bold">
            End date and time
            <input v-model="endAt" type="datetime-local" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" />
          </label>
        </div>
      </section>

      <section class="mb-6" aria-labelledby="requested-heading">
        <div class="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 id="requested-heading" class="mb-1 text-2xl font-bold leading-tight sm:text-3xl">
              Requested equipment
            </h2>
            <p class="text-xs font-medium text-ink/60">Add a row for each piece of equipment the event needs.</p>
          </div>
          <BauhausButton type="button" variant="outline" @click="addItem">Add item</BauhausButton>
        </div>

        <ul class="flex flex-col gap-3">
          <li v-for="(item, index) in items" :key="index" class="grid grid-cols-1 gap-4 border-2 border-ink bg-canvas p-4 shadow-hard sm:grid-cols-[1fr_1fr_7rem_auto] sm:items-end sm:border-4">
            <label class="flex flex-col gap-2 text-xs font-bold">
              Equipment ID / type
              <select v-model="item.equipmentId" :disabled="!catalogue.length" class="border-2 border-ink bg-canvas px-3 py-3 text-sm font-medium outline-none focus:bg-bauhaus-yellow/20 disabled:opacity-60">
                <option v-if="!catalogue.length" :value="null">{{ catalogueLoading ? "Loading equipment…" : "No equipment available" }}</option>
                <option v-for="equipment in catalogue" :key="equipment.equipment_id" :value="equipment.equipment_id">
                  {{ equipment.name }} · {{ equipment.equipment_type }}
                </option>
              </select>
            </label>
            <label class="flex flex-col gap-2 text-xs font-bold">
              Needed
              <input v-model.number="item.quantityNeeded" type="number" min="1" class="border-2 border-ink bg-canvas px-3 py-3 text-sm font-medium outline-none focus:bg-bauhaus-yellow/20" />
            </label>
            <button type="button" class="border-2 border-ink px-3 py-3 text-xs font-bold active-press hover:bg-bauhaus-red hover:text-canvas disabled:cursor-not-allowed disabled:opacity-40" :disabled="items.length === 1" @click="removeItem(index)">
              Remove
            </button>
          </li>
        </ul>
      </section>

      <div class="flex flex-col gap-4">
        <p v-if="catalogueError" class="border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">{{ catalogueError }}</p>
        <p v-if="validationMessage" class="border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">{{ validationMessage }}</p>
        <p v-if="errorMessage" class="border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4" role="alert">{{ errorMessage }}</p>

        <BauhausButton type="button" variant="secondary" full-width :disabled="isLoading || !catalogue.length" @click="checkAvailability">
          <span v-if="isLoading" class="h-4 w-4 animate-spin rounded-full border-2 border-canvas border-t-transparent" aria-hidden="true"></span>
          {{ isLoading ? "Checking availability" : "Check real-time availability" }}
        </BauhausButton>
      </div>

      <section v-if="results" class="mt-10" aria-labelledby="result-heading">
        <div class="mb-4 flex flex-wrap items-end justify-between gap-4">
          <h2 id="result-heading" class="text-2xl font-bold leading-tight sm:text-3xl">
            Equipment status
          </h2>
          <span class="border-2 border-ink px-4 py-2 text-xs font-bold" :class="results.sufficient ? pillClasses.green : pillClasses.red">{{ statusLabel }}</span>
        </div>

        <div class="overflow-x-auto border-2 border-ink bg-canvas shadow-hard sm:border-4">
          <table class="w-full min-w-[34rem] text-left text-sm">
            <thead class="bg-ink text-canvas">
              <tr class="text-xs">
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
                <td class="px-4 py-4 font-bold" :class="item.sufficient ? 'text-bauhaus-green' : 'text-bauhaus-red'">{{ item.sufficient ? "Sufficient" : "Insufficient" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </main>
</template>
