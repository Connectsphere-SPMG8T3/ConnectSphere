<script setup>
import { onMounted } from "vue";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";
import EquipmentRequestQueue from "@/components/equipment/EquipmentRequestQueue.vue";
import { useEquipmentQueueStore } from "@/features/equipment/equipmentQueueStore";

const breadcrumbItems = [
  { label: "Dashboard", to: { name: "dashboard-tech-support" } },
  { label: "Equipment requests" },
];

// SCRUM-24: every equipment request line, as venue staff's booking requests page.
const queue = useEquipmentQueueStore();

onMounted(() => queue.load());
</script>

<template>
  <main class="py-8">
    <BauhausBreadcrumb :items="breadcrumbItems" />

    <h1 class="sr-only">Equipment requests</h1>

    <EquipmentRequestQueue :queue="queue" />
  </main>
</template>
