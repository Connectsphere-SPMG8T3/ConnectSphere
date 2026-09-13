import { createRouter, createWebHistory } from "vue-router";

import { ROLE_DASHBOARD_ROUTES, useAuthStore } from "@/stores/auth";

const routes = [
  {
    path: "/",
    redirect: "/login",
  },
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/LoginView.vue"),
    meta: { requiresAuth: false },
  },
  {
    path: "/profile/me",
    name: "profile",
    component: () => import("@/views/ProfileView.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/dashboard/organiser",
    name: "dashboard-organiser",
    component: () => import("@/views/dashboards/OrganiserDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_organiser"] },
  },
  {
    path: "/dashboard/coordinator",
    name: "dashboard-coordinator",
    component: () => import("@/views/dashboards/CoordinatorDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator"] },
  },
  {
    path: "/dashboard/venue-staff",
    name: "dashboard-venue-staff",
    component: () => import("@/views/dashboards/VenueStaffDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["venue_staff"] },
  },
  {
    path: "/dashboard/tech-support",
    name: "dashboard-tech-support",
    component: () => import("@/views/dashboards/TechSupportDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["tech_support"] },
  },
  {
    path: "/dashboard/attendee",
    name: "dashboard-attendee",
    component: () => import("@/views/dashboards/AttendeeDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["attendee"] },
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/login",
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();

  if (authStore.token && !authStore.profile) {
    try {
      await authStore.fetchProfile();
    } catch {
      // Session is stale or the token has been revoked server-side.
    }
  }

  const isAuthenticated = authStore.isAuthenticated;

  if (to.name === "login" && isAuthenticated) {
    return authStore.dashboardPath;
  }

  if (to.meta.requiresAuth && !isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }

  if (to.meta.allowedRoles && !to.meta.allowedRoles.includes(authStore.role)) {
    return authStore.dashboardPath ?? "/login";
  }

  return true;
});

export { ROLE_DASHBOARD_ROUTES };
export default router;
