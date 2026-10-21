<script setup>
import { onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import VenueStaffBookingRequests from "@/components/venues/VenueStaffBookingRequests.vue";
import { useVenueStaffDashboardStore } from "@/features/venues/venueStaffDashboardStore";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const dashboard = useVenueStaffDashboardStore();

onMounted(() => dashboard.load());
</script>

<template>
  <main class="py-12">
    <p
      v-if="dashboard.error"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4"
      role="alert"
    >
      {{ dashboard.error }}
    </p>

    <BauhausCard background="yellow" accent="none" class="mb-10">
      <div class="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p class="text-xs font-bold text-ink/70">Venue Staff</p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">
            Booking requests
          </h1>
          <p class="mt-3 max-w-2xl text-sm font-medium">
            Review pending holds, re-reviews, and resolved booking decisions across every venue.
          </p>
        </div>
        <RouterLink
          :to="{ name: 'dashboard-venue-staff' }"
          class="border-2 border-ink bg-canvas px-4 py-3 text-center text-xs font-bold shadow-hard hover:bg-muted active-press sm:border-4"
        >
          Back to dashboard
        </RouterLink>
      </div>
    </BauhausCard>

    <VenueStaffBookingRequests :dashboard="dashboard" />
  </main>
</template>
