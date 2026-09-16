<script setup>
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const metrics = [
  { label: "Active Event Requests", value: "3", background: "red", accent: "circle", accentColor: "bauhaus-yellow" },
  { label: "Pending Coordinator Review", value: "1", background: "white", accent: "square", accentColor: "bauhaus-blue" },
  { label: "Confirmed Events", value: "7", background: "blue", accent: "triangle", accentColor: "bauhaus-yellow" },
];
</script>

<template>
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Event Organiser Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Track your event requests, liaise with your coordinator, and monitor progress toward launch —
        all from one place.
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
