<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import EventDetailPage from "@/components/registrations/EventDetailPage.vue";
import { showToast } from "@/composables/useToast";
import { useRegistrationStore } from "@/features/registrations/store";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useRegistrationStore();
const event = computed(() => store.event);
const isCheckingRegistration = ref(auth.isAuthenticated && auth.role === "attendee");
const showHeader = computed(() => !auth.isAuthenticated || auth.role !== "attendee");

const availabilityLabels = {
  open: "Registration open",
  not_open: "Registration not open yet",
  closed: "Registration closed",
  full: "Full",
};
const canRegister = computed(() => event.value?.availability === "open");
const hasRegistered = computed(() =>
  ["registered", "already_registered"].includes(store.registrationResult?.status) ||
  store.myRegistrations.some(({ event: registrationEvent, status }) =>
    registrationEvent?.id === route.params.id && status === "registered",
  ),
);
const mustChooseAttendeeRole = computed(() => auth.isAuthenticated && auth.role !== "attendee");

async function handleRegister() {
  if (!auth.isAuthenticated) {
    await router.push({ name: "login", query: { redirect: route.fullPath } });
    return;
  }
  if (mustChooseAttendeeRole.value) return;
  try {
    const result = await store.register(route.params.id);
    showToast(result.status === "already_registered"
      ? "You are already registered for this event."
      : "You are registered for this event.");
  } catch {
    return;
  }
}

onMounted(() => {
  store.loadEvent(route.params.id).catch(() => {});
  if (isCheckingRegistration.value) {
    store.loadMyRegistrations()
      .catch(() => {})
      .finally(() => {
        isCheckingRegistration.value = false;
      });
  }
});
</script>

<template>
  <div class="min-h-screen bg-canvas text-ink">
    <EventDetailPage
      :event="event"
      :loading="store.isLoading"
      :error="event ? '' : store.error"
      :show-header="showHeader"
      back-label="All events"
      back-to="/"
    >
      <template #sidebar>
        <h2 class="text-lg font-bold">
          {{ availabilityLabels[event.availability] || "Registration unavailable" }}
        </h2>
        <p v-if="event.effective_capacity" class="mt-3 text-sm font-medium">
          {{ event.registered_count }} of {{ event.effective_capacity }} places registered
        </p>
        <p v-if="store.error" role="alert" class="mt-4 border-2 border-ink bg-bauhaus-red p-3 text-sm font-bold text-canvas">
          {{ store.error }}
        </p>
        <p v-if="store.myRegistrationsError" role="alert" class="mt-4 border-2 border-ink bg-bauhaus-red p-3 text-sm font-bold text-canvas">
          {{ store.myRegistrationsError }}
        </p>
        <p v-if="mustChooseAttendeeRole" class="mt-4 text-sm font-bold">
          Switch your active role to Attendee to register.
        </p>
        <BauhausButton v-if="hasRegistered" class="mt-5 w-full" variant="primary" disabled>
          Registered
        </BauhausButton>
        <BauhausButton
          v-else-if="canRegister"
          class="mt-5 w-full"
          variant="primary"
          :disabled="store.isRegistering || mustChooseAttendeeRole || isCheckingRegistration"
          @click="handleRegister"
        >
          {{ store.isRegistering ? "Registering…" : "Register" }}
        </BauhausButton>
        <BauhausButton
          v-else-if="event.availability === 'full' && event.waitlist_enabled"
          class="mt-5 w-full"
          variant="secondary"
          disabled
        >
          Join waitlist
        </BauhausButton>
        <RouterLink
          v-else-if="event.availability === 'not_open' && !auth.isAuthenticated"
          :to="{ name: 'signup', params: { role: 'attendee' }, query: { redirect: route.fullPath } }"
          class="mt-5 block text-sm font-bold underline decoration-2 underline-offset-4"
        >Create an Attendee account</RouterLink>
      </template>
    </EventDetailPage>
  </div>
</template>