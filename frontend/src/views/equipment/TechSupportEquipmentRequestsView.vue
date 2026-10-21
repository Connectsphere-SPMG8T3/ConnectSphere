<script setup>
import { onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import EquipmentRequestQueue from "@/components/equipment/EquipmentRequestQueue.vue";
import { useEquipmentQueueStore } from "@/features/equipment/equipmentQueueStore";

// SCRUM-24: every equipment request line, as venue staff's booking requests page.
const queue = useEquipmentQueueStore();

onMounted(() => queue.load());
</script>

<template>
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-xs font-bold text-ink/70">Technical Support</p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">Equipment requests</h1>
          <p class="mt-3 max-w-2xl text-sm font-medium">
            Reserve, refuse and annotate equipment lines across every open event. Open a line to arrange its event.
          </p>
        </div>
        <RouterLink
          :to="{ name: 'dashboard-tech-support' }"
          class="border-2 border-ink bg-canvas px-4 py-3 text-center text-xs font-bold shadow-hard hover:bg-muted active-press sm:border-4"
        >
          Back to dashboard
        </RouterLink>
      </div>
    </BauhausCard>

    <EquipmentRequestQueue :queue="queue" />
  </main>
</template>
