<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BrandMark from "@/components/common/BrandMark.vue";
import RoleSwitcher from "@/components/common/RoleSwitcher.vue";
import { useMediaQuery } from "@/composables/useMediaQuery";
import { useSidebarState } from "@/composables/useSidebarState";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();
const { isCollapsed, isMobileOpen } = useSidebarState();

// Wider screens show the role switcher in the top bar instead.
const isWide = useMediaQuery("(min-width: 640px)");

watch(
  () => route.fullPath,
  () => {
    isMobileOpen.value = false;
  },
);

// Must stay in sync with the /venues route's allowedRoles in router/index.js.
const showVenuesLink = computed(() =>
  ["event_coordinator", "venue_staff"].includes(authStore.role),
);
const showVenueStaffRequests = computed(() => authStore.role === "venue_staff");
// Organisers and coordinators get Overview/Events views of their dashboard;
// each dashboard reads the tab from the route.
const EVENT_VIEW_DASHBOARDS = {
  event_organiser: "dashboard-organiser",
  event_coordinator: "dashboard-coordinator",
};
const eventViewsDashboard = computed(() => EVENT_VIEW_DASHBOARDS[authStore.role] ?? null);
const showTechSupportViews = computed(() => authStore.role === "tech_support");

const isDashboardActive = computed(() => route.path === authStore.dashboardPath);
const isVenueStaffRequestsActive = computed(() => route.name === "dashboard-venue-staff-requests");
const isEventOverviewActive = computed(
  () => route.name === eventViewsDashboard.value && route.query.tab !== "events",
);
const isEventListActive = computed(
  () => route.name === eventViewsDashboard.value && route.query.tab === "events",
);
// Must stay in sync with the tab names TechSupportDashboard reads from the query.
// Inventory is the default view, so it is active unless availability is asked for.
const isTechSupportInventoryActive = computed(
  () => route.name === "dashboard-tech-support" && route.query.tab !== "availability",
);
const isTechSupportRequestsActive = computed(() => route.name === "dashboard-tech-support-requests");
const isTechSupportAvailabilityActive = computed(
  () => route.name === "dashboard-tech-support" && route.query.tab === "availability",
);
const isProfileActive = computed(() => route.name === "profile");
const isVenuesActive = computed(
  () => route.name === "venue-search" || route.name === "venue-detail",
);

function navLinkClass(active) {
  return [
    "flex items-center gap-3 border-2 border-ink px-4 py-3 text-sm font-bold   transition-transform sm:border-4",
    active ? "bg-bauhaus-yellow text-ink shadow-hard hover:bg-muted" : "bg-canvas text-ink hover:bg-muted",
    // The collapsed rail is only 80px wide, so items drop their own side padding
    // and centre the icon instead — otherwise they outgrow the rail.
    isCollapsed.value ? "sm:justify-center sm:px-0" : "",
  ];
}

const labelClass = computed(() => (isCollapsed.value ? "sm:hidden" : ""));
const sectionPadClass = computed(() => (isCollapsed.value ? "sm:px-3" : "sm:px-6"));

async function handleLogout() {
  await authStore.logout();
  router.push({ name: "login" });
}
</script>

<template>
  <div
    v-if="isMobileOpen"
    class="fixed inset-0 z-30 bg-ink/50 sm:hidden"
    @click="isMobileOpen = false"
  ></div>

  <aside
    class="fixed inset-y-0 left-0 z-40 flex w-64 -translate-x-full flex-col border-r-2 border-ink bg-canvas shadow-hard transition-all duration-200 ease-out sm:translate-x-0 sm:border-r-4"
    :class="[isMobileOpen ? 'translate-x-0' : '-translate-x-full', isCollapsed ? 'sm:w-20' : 'sm:w-64']"
  >
    <button
      type="button"
      class="absolute -right-3 top-6 z-50 hidden h-6 w-6 items-center justify-center border-2 border-ink bg-canvas shadow-hard hover:bg-muted active-press sm:flex"
      :aria-label="isCollapsed ? 'Expand navigation' : 'Collapse navigation'"
      :aria-expanded="!isCollapsed"
      @click="isCollapsed = !isCollapsed"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="h-3 w-3 transition-transform"
        :class="isCollapsed ? 'rotate-180' : ''"
        aria-hidden="true"
      >
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>

    <!-- Same height as TopBar (h-20, borders included), so the two bottom
         rules read as one line across the sidebar and the page. -->
    <div
      class="flex items-center border-b-2 border-ink px-4 py-4 sm:h-20 sm:border-b-4 sm:py-0"
      :class="sectionPadClass"
    >
      <RouterLink
        :to="authStore.dashboardPath"
        class="flex w-full items-center gap-3"
        :class="isCollapsed ? 'sm:justify-center' : ''"
      >
        <BrandMark />
        <span
          class="text-lg font-bold leading-tight"
          :class="labelClass"
          >ConnectSphere</span
        >
      </RouterLink>
    </div>

    <nav
      class="flex flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden px-4 py-6"
      :class="sectionPadClass"
    >
      <template v-if="eventViewsDashboard">
        <RouterLink
          :to="{ name: eventViewsDashboard, query: { tab: 'overview' } }"
          :class="navLinkClass(isEventOverviewActive)"
          title="Overview"
          aria-label="Overview"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="h-5 w-5 shrink-0"
            aria-hidden="true"
          >
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
          <span :class="labelClass">Overview</span>
        </RouterLink>

        <RouterLink
          :to="{ name: eventViewsDashboard, query: { tab: 'events' } }"
          :class="navLinkClass(isEventListActive)"
          title="Events"
          aria-label="Events"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="h-5 w-5 shrink-0"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="17" />
            <path d="M16 2v4M8 2v4M3 10h18" />
          </svg>
          <span :class="labelClass">Events</span>
        </RouterLink>
      </template>

      <template v-else-if="showTechSupportViews">
        <RouterLink
          :to="{ name: 'dashboard-tech-support', query: { tab: 'inventory' } }"
          :class="navLinkClass(isTechSupportInventoryActive)"
          title="Inventory"
          aria-label="Inventory"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="h-5 w-5 shrink-0"
            aria-hidden="true"
          >
            <path d="M3 7l9-4 9 4-9 4-9-4z" />
            <path d="M3 7v10l9 4 9-4V7" />
            <path d="M12 11v10" />
          </svg>
          <span :class="labelClass">Inventory</span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'dashboard-tech-support', query: { tab: 'availability' } }"
          :class="navLinkClass(isTechSupportAvailabilityActive)"
          title="Availability"
          aria-label="Availability"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="h-5 w-5 shrink-0"
            aria-hidden="true"
          >
            <rect x="3" y="4" width="18" height="17" />
            <path d="M16 2v4M8 2v4M3 10h18" />
            <path d="M9 15l2 2 4-4" />
          </svg>
          <span :class="labelClass">Availability</span>
        </RouterLink>

        <RouterLink
          :to="{ name: 'dashboard-tech-support-requests' }"
          :class="navLinkClass(isTechSupportRequestsActive)"
          title="Equipment requests"
          aria-label="Equipment requests"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="h-5 w-5 shrink-0"
            aria-hidden="true"
          >
            <path d="M9 4h6v3H9z" />
            <path d="M8 5H5v16h14V5h-3" />
            <path d="M8 12h8M8 16h5" />
          </svg>
          <span :class="labelClass">Equipment requests</span>
        </RouterLink>
      </template>

      <RouterLink
        v-else
        :to="authStore.dashboardPath"
        :class="navLinkClass(isDashboardActive)"
        title="Dashboard"
        aria-label="Dashboard"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-5 w-5 shrink-0"
          aria-hidden="true"
        >
          <path d="M3 11l9-8 9 8" />
          <path d="M5 10v10h5v-6h4v6h5V10" />
        </svg>
        <span :class="labelClass">Dashboard</span>
      </RouterLink>

      <RouterLink
        v-if="showVenueStaffRequests"
        :to="{ name: 'dashboard-venue-staff-requests' }"
        :class="navLinkClass(isVenueStaffRequestsActive)"
        title="Booking requests"
        aria-label="Booking requests"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-5 w-5 shrink-0"
          aria-hidden="true"
        >
          <path d="M4 5h16v14H4z" />
          <path d="M8 9h8M8 13h5" />
        </svg>
        <span :class="labelClass">Booking requests</span>
      </RouterLink>

      <RouterLink
        v-if="showVenuesLink"
        to="/venues"
        :class="navLinkClass(isVenuesActive)"
        title="Venues"
        aria-label="Venues"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-5 w-5 shrink-0"
          aria-hidden="true"
        >
          <path d="M12 21s7-6.5 7-11.5A7 7 0 1 0 5 9.5C5 14.5 12 21 12 21z" />
          <circle cx="12" cy="9.5" r="2.5" />
        </svg>
        <span :class="labelClass">Venues</span>
      </RouterLink>
    </nav>

    <div
      v-if="!isWide && authStore.hasMultipleRoles"
      class="border-t-2 border-ink px-4 py-4"
      :class="sectionPadClass"
    >
      <RoleSwitcher />
    </div>

    <div
      class="mt-auto flex flex-col gap-2 border-t-2 border-ink px-4 py-4 sm:border-t-4"
      :class="sectionPadClass"
    >
      <RouterLink
        to="/profile/me"
        :class="navLinkClass(isProfileActive)"
        title="Profile"
        aria-label="Profile"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-5 w-5 shrink-0"
          aria-hidden="true"
        >
          <circle cx="12" cy="8" r="4" />
          <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
        </svg>
        <span :class="labelClass">Profile</span>
      </RouterLink>

      <button
        type="button"
        :class="navLinkClass(false)"
        title="Logout"
        aria-label="Logout"
        @click="handleLogout"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-5 w-5 shrink-0"
          aria-hidden="true"
        >
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="M16 17l5-5-5-5" />
          <path d="M21 12H9" />
        </svg>
        <span :class="labelClass">Logout</span>
      </button>
    </div>
  </aside>
</template>
