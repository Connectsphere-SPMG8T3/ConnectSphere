<script setup>
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const metrics = [
  { label: "Equipment Reservations", value: "8", background: "yellow", accent: "circle", accentColor: "ink" },
  { label: "Items in Catalogue", value: "34", background: "white", accent: "square", accentColor: "bauhaus-red" },
  { label: "On-Site Support Requests", value: "3", background: "blue", accent: "triangle", accentColor: "bauhaus-yellow" },
];
</script>

<template>
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Technical Support Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Manage technical equipment, action reservations, and coordinate on-site support for
        upcoming events.
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
