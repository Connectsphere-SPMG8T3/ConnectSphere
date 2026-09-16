<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";

import Nav from "@/components/common/Nav.vue";
import { useSidebarState } from "@/composables/useSidebarState";

const route = useRoute();
const showSidebar = computed(() => route.meta.requiresAuth === true);
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
      <!-- Right gutter runs 8px wider than the left so the cards' hard shadows,
           which are cast to the right, end up with the same clear space. The
           mobile-only top padding clears the floating hamburger button. -->
      <div :class="showSidebar ? 'pl-4 pr-6 pt-6 sm:pl-8 sm:pr-10 sm:pt-0' : ''">
        <RouterView />
      </div>
    </div>
  </div>
</template>
