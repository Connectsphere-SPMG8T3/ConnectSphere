<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const router = useRouter();

const roleLabels = {
  event_organiser: "Event Organiser",
  event_coordinator: "Event Coordinator",
  venue_staff: "Venue Staff",
  tech_support: "Technical Support",
  attendee: "Attendee",
};

const roleLabel = computed(() => roleLabels[authStore.role] ?? "Guest");

async function handleLogout() {
  await authStore.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <header class="border-b-2 border-ink bg-canvas px-4 py-4 shadow-hard sm:border-b-4 sm:px-8">
    <div class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
      <RouterLink :to="authStore.dashboardPath" class="flex items-center gap-3">
        <span class="relative block h-9 w-9" aria-hidden="true">
          <span class="absolute left-0 top-0 h-5 w-5 rounded-full bg-bauhaus-red"></span>
          <span class="absolute right-0 top-0 h-5 w-5 bg-bauhaus-blue"></span>
          <span
            class="absolute bottom-0 left-1/2 h-0 w-0 -translate-x-1/2 border-b-[18px] border-l-[10px] border-r-[10px] border-b-bauhaus-yellow border-l-transparent border-r-transparent"
          ></span>
        </span>
        <span class="text-xl font-black uppercase tracking-tighter">ConnectSphere</span>
      </RouterLink>

      <div class="flex items-center gap-4">
        <RouterLink
          to="/profile/me"
          class="border-2 border-ink bg-bauhaus-yellow px-3 py-1.5 text-xs font-bold uppercase tracking-widest text-ink shadow-hard sm:border-4"
        >
          {{ roleLabel }}
        </RouterLink>
        <BauhausButton variant="outline" @click="handleLogout">Logout</BauhausButton>
      </div>
    </div>
  </header>
</template>
