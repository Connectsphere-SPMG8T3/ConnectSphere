<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

import BauhausNavbar from "@/components/common/BauhausNavbar.vue";

const route = useRoute();
const showNavbar = computed(() => route.meta.requiresAuth === true);
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <BauhausNavbar v-if="showNavbar" />
    <RouterView />
  </div>
</template>
