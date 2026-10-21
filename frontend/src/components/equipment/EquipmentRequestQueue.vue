<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import { REQUEST_STATUS_LABELS } from "@/features/equipment/equipmentRequest";
import {
  ALL_ITEMS,
  equipmentFilterOptions,
  filterRequests,
  isWaiting,
  REQUEST_SORT_OPTIONS,
  requestStatusFilterOptions,
  sortRequests,
  WAITING,
  waitingDays,
} from "@/features/equipment/requestList";
import { formatTechnicalTime } from "@/features/equipment/technical";

// SCRUM-24: tech support's equipment request lines across every open event,
// shaped like venue staff's booking requests. Lines waiting on a decision come
// first; resolved ones stay available for reference. Each opens its event's
// technical page, where it is arranged.
const props = defineProps({
  queue: { type: Object, required: true },
});

const status = ref(WAITING);
const equipmentId = ref(ALL_ITEMS);
const sort = ref("event_soonest");
const startDate = ref("");
const endDate = ref("");

const statusOptions = computed(() => requestStatusFilterOptions(props.queue.lines));
const itemOptions = computed(() => equipmentFilterOptions(props.queue.lines));
const visible = computed(() =>
  sortRequests(
    filterRequests(props.queue.lines, {
      status: status.value,
      equipmentId: equipmentId.value,
      startDate: startDate.value,
      endDate: endDate.value,
    }),
    sort.value,
  ),
);

// Static class names: Tailwind can't see built ones. Yellow waits on you,
// blue is settled, red is refused or released (as on venue staff's list).
const CARD_TONES = { pending: "yellow", re_review: "yellow", reserved: "blue", rejected: "red", released: "red" };
const tone = (line) => CARD_TONES[line.status] ?? "blue";

const emptyDetail = computed(() =>
  props.queue.error
    ? "The equipment requests could not be loaded, so nothing is shown rather than a list it cannot stand behind."
    : "Nothing matches these filters. Waiting lines appear here as coordinators submit them.",
);
</script>

<template>
  <section aria-labelledby="equipment-requests-heading">
    <h2 id="equipment-requests-heading" class="mb-1 text-2xl font-bold leading-tight sm:text-3xl">
      Equipment requests
    </h2>
    <p class="mb-4 text-xs font-medium text-ink/60">
      Lines waiting on you appear first. Reserved, not available and released lines remain available for reference.
    </p>

    <p v-if="queue.error" role="alert" class="mb-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
      {{ queue.error }}
    </p>

    <div class="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <BauhausSelect v-model="status" label="Status" :options="statusOptions" :show-placeholder="false" compact />
      <BauhausSelect v-model="equipmentId" label="Equipment" :options="itemOptions" :show-placeholder="false" compact />
      <BauhausSelect v-model="sort" label="Sort by" :options="REQUEST_SORT_OPTIONS" :show-placeholder="false" compact />
      <BauhausInput v-model="startDate" type="date" label="From date" compact />
      <BauhausInput v-model="endDate" type="date" label="To date" compact />
    </div>

    <div
      v-if="queue.isLoading && !queue.lines.length"
      class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold text-ink/70 sm:border-4"
      role="status"
    >
      <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
      Loading requests
    </div>

    <ol v-else-if="visible.length" class="grid grid-cols-1 gap-4">
      <li v-for="line in visible" :key="line.id">
        <BauhausCard
          :background="tone(line)"
          accent="none"
          compact
          allow-overflow
          data-testid="equipment-request-card"
          :data-request-status="line.status"
          class="border-4 shadow-none hover:bg-muted focus-within:bg-muted transition duration-150 hover:-translate-y-0.5 focus-within:-translate-y-0.5 motion-reduce:transition-none"
        >
          <RouterLink :to="{ name: 'tech-support-event', params: { id: line.event_id } }" class="flex flex-col gap-2 active-press">
            <div class="flex flex-wrap items-baseline justify-between gap-4">
              <span class="text-xl font-bold leading-tight">
                {{ line.equipment_name }} <span class="font-bold">× {{ line.quantity }}</span>
              </span>
              <span class="text-xs font-bold text-ink/70">
                {{ line.equipment_type || "Type not set" }} · {{ REQUEST_STATUS_LABELS[line.status] ?? line.status }}
              </span>
            </div>
            <span class="text-sm font-bold">{{ line.event_name }} · {{ formatTechnicalTime(line.event_starts_at) }}</span>
            <p v-if="line.technical_requirements" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm font-medium text-ink/75">
              {{ line.technical_requirements }}
            </p>
            <span class="text-xs font-bold text-ink/55">
              {{ line.requested_by?.full_name ?? "Unknown user" }}
              <template v-if="isWaiting(line)"> · Waiting {{ waitingDays(line) ?? "—" }} days</template>
            </span>
            <span v-if="line.not_available_reason" class="border-t-2 border-ink/20 pt-2 text-xs font-medium text-ink/70 [overflow-wrap:anywhere]">
              Not available: {{ line.not_available_reason }}
            </span>
          </RouterLink>
        </BauhausCard>
      </li>
    </ol>

    <BauhausEmptyState v-else :title="queue.error ? 'Requests unavailable' : 'No matching requests'" :detail="emptyDetail" />
  </section>
</template>
