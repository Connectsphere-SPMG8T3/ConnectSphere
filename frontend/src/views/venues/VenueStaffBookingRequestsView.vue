<script setup>
import { onMounted } from "vue";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";
import VenueStaffBookingRequests from "@/components/venues/VenueStaffBookingRequests.vue";
import { useVenueStaffDashboardStore } from "@/features/venues/venueStaffDashboardStore";
import { useAuthStore } from "@/stores/auth";

const breadcrumbItems = [
  { label: "Dashboard", to: { name: "dashboard-venue-staff" } },
  { label: "Booking requests" },
];

const authStore = useAuthStore();
const dashboard = useVenueStaffDashboardStore();

onMounted(() => dashboard.load());
</script>

<template>
  <main class="py-8">
    <BauhausBreadcrumb :items="breadcrumbItems" />

    <p
      v-if="dashboard.error"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4"
      role="alert"
    >
      {{ dashboard.error }}
    </p>

    <h1 class="sr-only">Booking requests</h1>

    <VenueStaffBookingRequests :dashboard="dashboard" />
  </main>
</template>
