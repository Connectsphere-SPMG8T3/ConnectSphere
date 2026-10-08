<script setup>
// 12 AC12: placeholder. The role exists so later Lead stories can grant it access.
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
</script>

<template>
  <main class="py-12">
    <BauhausCard background="blue" accent="none">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event Coordinator Lead Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">Your tools will appear here as they are built.</p>
    </BauhausCard>
  </main>
</template>
