<script setup>
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const metrics = [
  { label: "Requests Awaiting Review", value: "5", background: "blue", accent: "circle", accentColor: "bauhaus-yellow" },
  { label: "Venues to Coordinate", value: "4", background: "white", accent: "square", accentColor: "bauhaus-red" },
  { label: "Events in Progress", value: "9", background: "red", accent: "triangle", accentColor: "bauhaus-yellow" },
];
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="blue" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event Coordinator Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Review event requests, coordinate venues and equipment, and keep organisers up to date on
        progress.
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
  </main>
</template>
