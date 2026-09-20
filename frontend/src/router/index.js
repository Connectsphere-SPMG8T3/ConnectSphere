import { createRouter, createWebHistory } from "vue-router";

import { ROLE_DASHBOARD_ROUTES, useAuthStore } from "@/stores/auth";

const UNSUPPORTED_ROLE_MESSAGE = "Your account can't be opened in this app. Please contact support.";

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
    path: "/events/new",
    name: "event-new",
    component: () => import("@/views/events/EventRequestView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_organiser"] },
  },
  {
    path: "/events/:id",
    name: "event-detail",
    component: () => import("@/views/events/EventDetailView.vue"),
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
    path: "/venues",
    name: "venue-search",
    component: () => import("@/views/venues/VenueSearchView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator", "venue_staff"] },
  },
  {
    path: "/venues/:id",
    name: "venue-detail",
    component: () => import("@/views/venues/VenueDetailView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator", "venue_staff"] },
  },
  {
    // A placeholder until SCRUM-19/20 build the request view and the
    // approve/reject decision. Venue staff only for now: the coordinator side
    // of this page arrives with those stories, and granting access to an empty
    // state early buys nothing.
    path: "/bookings/:id",
    name: "booking-request",
    component: () => import("@/views/bookings/BookingRequestView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["venue_staff"] },
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

  // Verify a stored session once per page load, renewing it if the access
  // token has expired. A session the server rejects is cleared, so the checks
  // below send the user to login.
  if (authStore.token && !authStore.sessionVerified) {
    try {
      await authStore.fetchProfile();
    } catch {
      // Handled by fetchProfile; a network error keeps the stored session.
    }
  }

  const isAuthenticated = authStore.isAuthenticated;

  // A session whose role has no dashboard (e.g. a stale stored profile) would
  // bounce between /login and its "dashboard" (also /login) forever.
  if (isAuthenticated && !ROLE_DASHBOARD_ROUTES[authStore.role]) {
    authStore.clearSession(UNSUPPORTED_ROLE_MESSAGE);
    return to.name === "login" ? true : { name: "login" };
  }

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
