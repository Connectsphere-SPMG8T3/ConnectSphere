<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import BrandMark from "@/components/common/BrandMark.vue";
import { formatFriendlyDate } from "@/components/common/dateFormat";
import NotificationBell from "@/components/common/NotificationBell.vue";
import { useSidebarState } from "@/composables/useSidebarState";
import { useAuthStore } from "@/stores/auth";
import { useVenuesStore } from "@/features/venues/venueSearchStore";

const authStore = useAuthStore();
const venuesStore = useVenuesStore();
const router = useRouter();
const { isMobileOpen } = useSidebarState();

// "Hello Jack" reads as a greeting; the full stored name reads as a form
// field, so only the first word is used.
const firstName = computed(() => authStore.profile?.full_name?.trim().split(/\s+/)[0] ?? "");

// The bar is mounted for the life of the session, so the date is read once at
// mount. A session left open across midnight shows yesterday until the next
// navigation — accepted rather than running a timer for it.
const today = formatFriendlyDate(new Date());

const query = ref("");

// Search goes to the venue catalogue, which is the only searchable collection
// that exists today, so it is only offered to the roles allowed there. Must
// stay in sync with the /venues route's allowedRoles in router/index.js.
const showSearch = computed(() => ["event_coordinator", "venue_staff"].includes(authStore.role));

async function handleSearch() {
  const location = query.value.trim();
  if (!location) return;
  venuesStore.criteria.location = location;
  await router.push("/venues");
  // Pushed route or not, the view only searches on its first mount, so the
  // store is asked directly — otherwise a search typed while already on
  // /venues would change nothing.
  await venuesStore.search();
}
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
        <p class="truncate text-base font-black uppercase tracking-tighter sm:text-xl">
          Hello {{ firstName }}!
        </p>
        <p
          class="whitespace-nowrap text-[11px] font-bold uppercase tracking-widest text-ink/60 sm:text-xs"
        >
          {{ today }}
        </p>
      </div>

      <div class="ml-auto flex items-center gap-2 sm:gap-4">
        <NotificationBell />

        <form
          v-if="showSearch"
          role="search"
          class="hidden items-center border-2 border-ink bg-canvas shadow-hard focus-within:bg-bauhaus-yellow/20 sm:flex"
          @submit.prevent="handleSearch"
        >
          <button
            type="submit"
            class="flex h-10 w-10 shrink-0 items-center justify-center active-press"
            aria-label="Run search"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="h-5 w-5"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.5-3.5" />
            </svg>
          </button>
          <input
            v-model="query"
            type="search"
            aria-label="Search"
            placeholder="Search"
            class="w-40 bg-transparent py-2 pr-4 text-sm font-medium text-ink outline-none placeholder:text-ink/40 lg:w-56"
          />
        </form>
        <button
          type="button"
          class="flex h-10 w-10 items-center justify-center border-2 border-ink bg-canvas shadow-hard active-press sm:hidden"
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
