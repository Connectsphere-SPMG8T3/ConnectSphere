<script setup>
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const metrics = [
  { label: "Venues Managed", value: "12", background: "red", accent: "circle", accentColor: "bauhaus-yellow" },
  { label: "Booking Requests", value: "6", background: "white", accent: "square", accentColor: "bauhaus-blue" },
  { label: "Availability Updates Due", value: "2", background: "yellow", accent: "triangle", accentColor: "ink" },
];
</script>

<template>
  <main class="py-12">
    <BauhausCard background="red" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Venue Staff Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Manage the venue catalogue, review booking requests, and keep availability and layouts
        current.
      </p>
    </BauhausCard>

    <div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
      <BauhausCard
        v-for="metric in metrics"
        :key="metric.label"
        :background="metric.background"
        :accent="metric.accent"
        :accent-color="metric.accentColor"
      >
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">{{ metric.label }}</p>
        <p class="mt-2 text-5xl font-black tracking-tighter">{{ metric.value }}</p>
      </BauhausCard>
    </div>
    <div class="mt-10 flex flex-wrap gap-4">
      <RouterLink to="/venues">
        <BauhausButton variant="secondary">Search venues</BauhausButton>
      </RouterLink>
    </div>
  </main>
</template>
