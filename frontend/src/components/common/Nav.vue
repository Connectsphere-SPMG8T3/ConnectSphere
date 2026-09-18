<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausSelect from "@/components/common/BauhausSelect.vue";
import BrandMark from "@/components/common/BrandMark.vue";
import { useSidebarState } from "@/composables/useSidebarState";
import { ROLE_LABELS, useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();
const { isCollapsed, isMobileOpen } = useSidebarState();

const roleOptions = computed(() =>
  authStore.roles.map((role) => ({ value: role, label: ROLE_LABELS[role] ?? role })),
);

// BauhausSelect binds its native <select> with a plain :value/@change pair
// (not v-model), so the browser sets the visible selection imperatively the
// instant the user picks an option, before this handler even runs. When the
// switch is a no-op or fails, authStore.role never changes — nothing
// reactive fires — so nothing corrects that DOM value on its own; bumping
// this key forces BauhausSelect to remount and re-apply the current role.
// Only bumped on those two paths: a successful switch already changes
// authStore.role for real, so Vue's normal reactivity updates the select
// correctly without a remount — bumping unconditionally would remount (and
// flicker) on every switch, not just the ones that need correcting.
const roleSwitcherKey = ref(0);

async function handleRoleChange(role) {
  // BauhausSelect always renders an empty placeholder option, and re-selecting
  // the already-active role should be a no-op rather than a round-trip.
  if (!role || role === authStore.role) {
    roleSwitcherKey.value += 1;
    return;
  }
  try {
    await authStore.setActiveRole(role);
    await router.push(authStore.dashboardPath);
  } catch {
    // Switch rejected (e.g. role no longer held): authStore.role is
    // unchanged, so force the remount to redisplay it correctly.
    roleSwitcherKey.value += 1;
  }
}

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

const isDashboardActive = computed(() => route.name?.startsWith("dashboard-"));
const isProfileActive = computed(() => route.name === "profile");
const isVenuesActive = computed(
  () => route.name === "venue-search" || route.name === "venue-detail",
);

function navLinkClass(active) {
  return [
    "flex items-center gap-3 border-2 border-ink px-4 py-3 text-sm font-bold uppercase tracking-wide transition-transform sm:border-4",
    active ? "bg-bauhaus-yellow text-ink shadow-hard" : "bg-canvas text-ink hover:bg-muted",
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
      class="absolute -right-3 top-6 z-50 hidden h-6 w-6 items-center justify-center border-2 border-ink bg-canvas shadow-hard active-press sm:flex"
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
          class="text-lg font-black uppercase leading-tight tracking-tighter"
          :class="labelClass"
          >ConnectSphere</span
        >
      </RouterLink>
    </div>

    <nav
      class="flex flex-1 flex-col gap-2 overflow-y-auto overflow-x-hidden px-4 py-6"
      :class="sectionPadClass"
    >
      <RouterLink
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
      v-if="authStore.hasMultipleRoles"
      data-testid="role-switcher"
      class="border-t-2 border-ink px-4 py-4 sm:border-t-4"
      :class="[sectionPadClass, isCollapsed ? 'sm:hidden' : '']"
    >
      <BauhausSelect
        :key="roleSwitcherKey"
        label="Acting as"
        :model-value="authStore.role"
        :options="roleOptions"
        placeholder="Select a role"
        @update:model-value="handleRoleChange"
      />
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
