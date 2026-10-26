<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

import Nav from "@/components/common/Nav.vue";
import TopBar from "@/components/common/TopBar.vue";
import Toast from "@/components/common/Toast.vue";
import { useSidebarState } from "@/composables/useSidebarState";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const auth = useAuthStore();
const showSidebar = computed(() =>
  (route.meta.requiresAuth === true && route.meta.standalone !== true) ||
  (route.meta.attendeeNavigation === true && auth.isAuthenticated && auth.role === "attendee"),
);
const { isCollapsed } = useSidebarState();

const contentOffsetClass = computed(() => {
  if (!showSidebar.value) return "";
  return isCollapsed.value ? "sm:pl-20" : "sm:pl-64";
});
</script>

<template>
  <div class="min-h-screen bg-canvas">
    <Nav v-if="showSidebar" />
    <div class="transition-[padding]" :class="contentOffsetClass">
      <!-- The top bar spans the content column edge to edge, so it sits
           outside the gutters below rather than inside them. -->
      <TopBar v-if="showSidebar" />
      <!-- Right gutter runs 8px wider than the left so the cards' hard shadows,
           which are cast to the right, end up with the same clear space. -->
      <div :class="showSidebar ? 'pl-4 pr-6 sm:pl-8 sm:pr-10' : ''">
        <RouterView />
      </div>
    </div>
    <Toast />
  </div>
</template>
