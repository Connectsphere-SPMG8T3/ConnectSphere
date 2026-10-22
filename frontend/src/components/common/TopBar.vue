<script setup>
import { computed } from "vue";

import BrandMark from "@/components/common/BrandMark.vue";
import { formatFriendlyDate } from "@/components/common/dateFormat";
import NotificationBell from "@/components/common/NotificationBell.vue";
import RoleSwitcher from "@/components/common/RoleSwitcher.vue";
import { useMediaQuery } from "@/composables/useMediaQuery";
import { useSidebarState } from "@/composables/useSidebarState";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const { isMobileOpen } = useSidebarState();

// "Hello Jack" reads as a greeting; the full stored name reads as a form
// field, so only the first word is used.
const firstName = computed(() => authStore.profile?.full_name?.trim().split(/\s+/)[0] ?? "");

// The bar is mounted for the life of the session, so the date is read once at
// mount. A session left open across midnight shows yesterday until the next
// navigation — accepted rather than running a timer for it.
const today = formatFriendlyDate(new Date());

// The menu holds the role switcher on phones, where the bar has no room for it.
const isWide = useMediaQuery("(min-width: 640px)");
</script>

<template>
  <!-- z-30 matches Nav's mobile scrim, and the bar is rendered after Nav, so
       the menu button stays lit and clickable while the drawer is open; the
       drawer itself is z-40 and still slides over the bar's left edge. -->
  <header class="sticky top-0 z-30 border-b-2 border-ink bg-surface sm:h-20 sm:border-b-4">
    <div class="flex items-center gap-3 px-4 py-3 sm:h-full sm:gap-6 sm:px-8 sm:py-0 sm:pr-10">
      <!-- On small screens the sidebar is a drawer, so the mark rides next to
           the greeting to keep the brand on screen. -->
      <RouterLink :to="authStore.dashboardPath" class="shrink-0 sm:hidden" aria-label="Dashboard">
        <BrandMark />
      </RouterLink>

      <div class="flex min-w-0 flex-col items-start gap-0.5">
        <p class="truncate text-base font-bold sm:text-xl">
          Hello {{ firstName }}!
        </p>
        <p
          class="whitespace-nowrap text-xs font-bold text-ink/70"
        >
          {{ today }}
        </p>
      </div>

      <div class="ml-auto flex items-center gap-2 sm:gap-4">
        <NotificationBell />

        <RoleSwitcher v-if="isWide" compact />
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center border-2 border-ink bg-canvas shadow-hard hover:bg-muted active-press sm:hidden"
          aria-label="Toggle navigation menu"
          :aria-expanded="isMobileOpen"
          @click="isMobileOpen = !isMobileOpen"
        >
          <span class="flex flex-col gap-1.5" aria-hidden="true">
            <span class="block h-0.5 w-6 bg-ink"></span>
            <span class="block h-0.5 w-6 bg-ink"></span>
            <span class="block h-0.5 w-6 bg-ink"></span>
          </span>
        </button>
      </div>
    </div>
  </header>
</template>
