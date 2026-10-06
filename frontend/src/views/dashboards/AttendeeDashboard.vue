<script setup>
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const metrics = [
  { label: "Upcoming Registrations", value: "2", background: "blue", accent: "circle", accentColor: "bauhaus-yellow" },
  { label: "Public Events Available", value: "18", background: "white", accent: "square", accentColor: "bauhaus-red" },
  { label: "Events Attended", value: "5", background: "red", accent: "triangle", accentColor: "bauhaus-yellow" },
];
</script>

<template>
  <main class="py-12">
    <BauhausCard background="blue" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Attendee Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Browse confirmed public events, register your attendance, and keep track of the events
        you're going to.
      </p>
    </BauhausCard>

    <div class="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
      <BauhausSummaryCard
        v-for="metric in metrics"
        :key="metric.label"
        :label="metric.label"
        :value="metric.value"
        :background="metric.background"
        :accent="metric.accent"
        :accent-color="metric.accentColor"
      />
    </div>
  </main>
</template>
