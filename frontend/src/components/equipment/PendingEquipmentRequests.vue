<script setup>
import { onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { REQUEST_STATUS_LABELS } from "@/features/equipment/equipmentRequest";
import { useEquipmentQueueStore } from "@/features/equipment/equipmentQueueStore";

// SCRUM-45: tech support's list of lines waiting on them, pending or flagged for
// re-review (SCRUM-24 AC7). Each opens its event, where it is arranged (SCRUM-24).
const store = useEquipmentQueueStore();

const formatter = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" });

function formatTime(value) {
  return value ? formatter.format(new Date(value)) : "Date not set";
}

onMounted(() => store.load());
</script>

<template>
  <div>
    <div v-if="store.isLoading && !store.lines.length" class="flex items-center gap-3 border-2 border-ink bg-canvas p-4 text-sm font-bold uppercase tracking-widest text-ink/70 sm:border-4" role="status">
      <span class="h-5 w-5 animate-spin rounded-full border-2 border-ink border-t-transparent" aria-hidden="true"></span>
      Loading requests
    </div>
    <p v-else-if="store.error" role="alert" class="border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
      {{ store.error }}
    </p>
    <ul v-else-if="store.lines.length" class="flex max-h-[28rem] flex-col gap-3 overflow-y-auto pb-1 pr-1">
      <li v-for="line in store.lines" :key="line.id" class="flex flex-col gap-2 border-2 border-ink bg-canvas p-4 shadow-hard sm:border-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <span class="text-base font-black uppercase leading-tight tracking-tighter">{{ line.equipment_name }} × {{ line.quantity }}</span>
          <span class="shrink-0 border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-ink">
            {{ REQUEST_STATUS_LABELS[line.status] ?? line.status }}
          </span>
        </div>
        <RouterLink
          :to="{ name: 'tech-support-event', params: { id: line.event_id } }"
          class="active-press self-start text-sm font-bold underline decoration-2 underline-offset-4 hover:text-bauhaus-blue"
        >
          {{ line.event_name }} · {{ formatTime(line.event_starts_at) }}
        </RouterLink>
        <p v-if="line.technical_requirements" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm font-medium text-ink/75">{{ line.technical_requirements }}</p>
        <span class="text-xs font-bold uppercase tracking-widest text-ink/55">
          {{ line.requested_by?.full_name ?? "Unknown user" }} · Submitted {{ formatTime(line.created_at) }}
        </span>
      </li>
    </ul>
    <BauhausEmptyState v-else title="No pending requests" detail="Equipment requests from coordinators appear here once submitted, and lines needing re-review after a time change." />
  </div>
</template>
