import { createRouter, createWebHistory } from "vue-router";

import { ROLE_DASHBOARD_ROUTES, useAuthStore } from "@/stores/auth";

const UNSUPPORTED_ROLE_MESSAGE = "Your account can't be opened in this app. Please contact support.";

const routes = [
  {
    path: "/safety/events/:id",
    name: "safety-review",
    component: () => import("@/views/events/SafetyReviewView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["safety_officer"] },
  },
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
    path: "/signup",
    redirect: "/signup/organiser",
    meta: { requiresAuth: false },
  },
  {
    path: "/signup/:role(organiser|attendee)",
    name: "signup",
    component: () => import("@/views/SignupView.vue"),
    props: (route) => ({ role: route.params.role === "attendee" ? "attendee" : "event_organiser" }),
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
    // SCRUM-34/52: the assigned coordinator's review page. SCRUM-49 extends it
    // with the full review details; the API enforces "assigned" (403 otherwise).
    path: "/coordinator/events/:id",
    name: "coordinator-event",
    component: () => import("@/views/events/CoordinatorEventView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator"] },
  },
  {
    // CR-101: the Event Coordinator Lead opens an event to assign or reassign
    // it. Lead only; the API checks the event is in this Lead's scope.
    path: "/lead/events/:id",
    name: "lead-event",
    component: () => import("@/views/events/LeadEventView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator_lead"] },
  },
  {
    path: "/dashboard/venue-staff",
    name: "dashboard-venue-staff",
    component: () => import("@/views/dashboards/VenueStaffDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["venue_staff"] },
  },
  {
    path: "/dashboard/venue-staff/requests",
    name: "dashboard-venue-staff-requests",
    component: () => import("@/views/venues/VenueStaffBookingRequestsView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["venue_staff"] },
  },
  {
    path: "/dashboard/tech-support",
    name: "dashboard-tech-support",
    component: () => import("@/views/dashboards/TechSupportDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["tech_support"] },
  },
  {
    // SCRUM-24: arrange one event's equipment.
    path: "/tech-support/events/:id",
    name: "tech-support-event",
    component: () => import("@/views/events/TechnicalEventView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["tech_support"] },
  },
  {
    path: "/dashboard/coordinator-lead",
    name: "dashboard-coordinator-lead",
    component: () => import("@/views/dashboards/CoordinatorLeadDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["event_coordinator_lead"] },
  },
  {
    path: "/dashboard/safety",
    name: "dashboard-safety",
    component: () => import("@/views/dashboards/SafetyDashboard.vue"),
    meta: { requiresAuth: true, allowedRoles: ["safety_officer"] },
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
    // SCRUM-63: venue staff manage the catalogue (QA-101); coordinators only
    // read and search it, so editing is narrower than the detail page above.
    path: "/venues/:id/edit",
    name: "venue-edit",
    component: () => import("@/views/venues/VenueEditView.vue"),
    meta: { requiresAuth: true, allowedRoles: ["venue_staff"] },
  },
  {
    // A placeholder until SCRUM-19/20 build the request view and the
    // approve/reject decision. Venue staff only for now: the coordinator side
    // of this page arrives with those stories, and granting access to an empty
    // state early buys nothing.
    path: "/bookings/:id",
    name: "booking-request",
    component: () => import("@/views/bookings/BookingRequestView.vue"),
    // SCRUM-38: the assigned coordinator reads why a booking was rejected; the API checks the assignment.
    meta: { requiresAuth: true, allowedRoles: ["venue_staff", "event_coordinator"] },
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

  // Signing in or up again makes no sense with a live session.
  if ((to.name === "login" || to.name === "signup") && isAuthenticated) {
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
