<script setup>
// CR-103 AC5: placeholder. The safety review queue (CR-103) replaces this page's body.
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
</script>

<template>
  <main class="py-12">
    <BauhausCard background="red" accent="none">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Safety Officer Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">Events waiting for a safety check will appear here.</p>
    </BauhausCard>
  </main>
</template>
