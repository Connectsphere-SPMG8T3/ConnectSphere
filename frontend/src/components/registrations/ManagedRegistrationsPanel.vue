<script setup>
import { computed, onMounted, ref, watch } from "vue";

import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import {
  buildManagedRegistrationsCsv,
  managedRegistrationStatusLabel,
} from "@/features/registrations/managedRegistrationsCsv";
import { registrationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const props = defineProps({
  eventId: {
    type: String,
    required: true,
  },
});

const auth = useAuthStore();
const report = ref(null);
const loading = ref(true);
const error = ref("");
const search = ref("");
const statusFilter = ref("");
const isCoordinator = computed(() => auth.role === "event_coordinator");
let requestSequence = 0;

const statuses = [
  ["registered", managedRegistrationStatusLabel("registered")],
  ["waitlisted", managedRegistrationStatusLabel("waitlisted")],
  ["invited", managedRegistrationStatusLabel("invited")],
  ["withdrawn", managedRegistrationStatusLabel("withdrawn")],
];

const filteredRegistrations = computed(() => {
  const query = search.value.trim().toLowerCase();
  return (report.value?.registrations ?? []).filter((registration) => {
    const matchesStatus = !statusFilter.value || registration.status === statusFilter.value;
    const matchesName = !query || registration.full_name.toLowerCase().includes(query);
    return matchesStatus && matchesName;
  });
});

async function loadReport() {
  const sequence = ++requestSequence;
  loading.value = true;
  error.value = "";
  try {
    const result = await auth.withSession((token) => registrationsApi.managedEvent(props.eventId, token));
    if (sequence === requestSequence) report.value = result;
  } catch (loadError) {
    if (sequence === requestSequence) {
      report.value = null;
      error.value = loadError.message || "Unable to load registrations. Please try again.";
    }
  } finally {
    if (sequence === requestSequence) loading.value = false;
  }
}

function exportCsv() {
  const csv = buildManagedRegistrationsCsv(report.value.registrations, isCoordinator.value);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `event-${props.eventId}-registrations.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

onMounted(loadReport);
watch(() => props.eventId, loadReport);
</script>

<template>
  <BauhausCard background="white" accent="none" data-testid="managed-registrations">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold">Registrations</h2>
        <p v-if="isCoordinator" class="mt-1 text-sm font-medium text-ink/70">
          Attendee contact details are visible to the assigned coordinator.
        </p>
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          type="button"
          class="border-2 border-ink bg-canvas px-3 py-2 text-sm font-bold shadow-hard"
          :disabled="loading"
          @click="loadReport"
        >
          Refresh
        </button>
        <button
          v-if="report"
          type="button"
          class="border-2 border-ink bg-canvas px-3 py-2 text-sm font-bold shadow-hard"
          :disabled="loading"
          @click="exportCsv"
        >
          Export CSV
        </button>
      </div>
    </div>

    <p v-if="loading" class="mt-5 text-sm font-medium" role="status">Loading registrations…</p>
    <div v-else-if="error" class="mt-5 border-2 border-ink bg-bauhaus-red p-4 text-sm font-bold text-canvas" role="alert">
      <p>{{ error }}</p>
      <button type="button" class="mt-3 underline" @click="loadReport">Try again</button>
    </div>

    <template v-else-if="report">
      <dl class="mt-5 grid grid-cols-3 gap-x-3 gap-y-4 border-y-2 border-ink py-4 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">
        <div>
          <dt class="text-xs font-bold text-ink/70">Registered</dt>
          <dd class="mt-1 text-xl font-bold">{{ report.registered_count }}</dd>
        </div>
        <div>
          <dt class="text-xs font-bold text-ink/70">Effective capacity</dt>
          <dd class="mt-1 text-xl font-bold">{{ report.effective_capacity ?? "No limit" }}</dd>
        </div>
        <div>
          <dt class="text-xs font-bold text-ink/70">Remaining places</dt>
          <dd class="mt-1 text-xl font-bold">{{ report.remaining_places ?? "No limit" }}</dd>
        </div>
        <div v-if="report.waitlist_count > 0">
          <dt class="text-xs font-bold text-ink/70">Waitlisted</dt>
          <dd class="mt-1 text-xl font-bold">{{ report.waitlist_count }}</dd>
        </div>
      </dl>

      <div class="mt-5 grid grid-cols-2 gap-3 sm:gap-4">
        <BauhausInput
          v-model="search"
          label="Search attendee name"
          placeholder="Enter a name"
          aria-label="Search attendee name"
          compact
        />
        <label class="flex flex-col gap-2">
          <span class="text-xs font-bold text-ink">Filter registration status</span>
          <select
            v-model="statusFilter"
            aria-label="Filter registration status"
            class="focus-tint h-[50px] border-2 border-ink bg-canvas px-4 text-base font-medium text-ink outline-none"
          >
            <option value="">All statuses</option>
            <option v-for="[value, label] in statuses" :key="value" :value="value">{{ label }}</option>
          </select>
        </label>
      </div>

      <p v-if="filteredRegistrations.length === 0" class="mt-5 text-sm font-medium">
        {{ report.registrations.length ? "No registrations match the selected filters." : "No registrations have been recorded yet." }}
      </p>
      <ul v-else class="mt-5 divide-y-2 divide-ink border-y-2 border-ink">
        <li
          v-for="registration in filteredRegistrations"
          :key="registration.id"
          class="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2 py-4"
        >
          <div class="min-w-0">
            <p class="break-words font-bold">{{ registration.full_name }}</p>
            <template v-if="isCoordinator">
              <p v-if="registration.email" class="mt-1 text-sm font-medium">{{ registration.email }}</p>
              <p v-if="registration.phone_number" class="mt-1 text-sm font-medium">{{ registration.phone_number }}</p>
            </template>
          </div>
          <span
            :aria-label="managedRegistrationStatusLabel(registration.status)"
            :title="managedRegistrationStatusLabel(registration.status)"
            class="block w-fit justify-self-end whitespace-nowrap border-2 border-ink bg-bauhaus-yellow px-2 py-1 text-right text-xs font-bold"
          >
            <span class="sm:hidden">{{ managedRegistrationStatusLabel(registration.status) }}</span>
            <span class="hidden sm:inline">{{ managedRegistrationStatusLabel(registration.status) }}</span>
          </span>
        </li>
      </ul>
    </template>
  </BauhausCard>
</template>
