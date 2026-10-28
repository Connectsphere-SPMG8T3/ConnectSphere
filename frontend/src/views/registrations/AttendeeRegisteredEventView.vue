<script setup>
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

import EventDetailPage from "@/components/registrations/EventDetailPage.vue";
import { registrationStatusLabel } from "@/features/registrations/registeredEvents";
import { useRegistrationStore } from "@/features/registrations/store";

const route = useRoute();
const registrationStore = useRegistrationStore();
const registration = computed(() =>
  registrationStore.myRegistrations.find(({ event }) => event.id === route.params.id),
);
const event = computed(() => registration.value?.event ?? null);

onMounted(() => registrationStore.loadMyRegistrations().catch(() => {}));
</script>

<template>
  <EventDetailPage
    :event="event"
    :loading="registrationStore.isLoadingMyRegistrations"
    :error="registrationStore.myRegistrationsError || ''"
    :show-header="false"
    empty-title="Event not found"
    empty-detail="This event is not in your current registrations."
    :back-to="{ name: 'dashboard-attendee', query: { tab: 'events' } }"
    back-label="Back to My events"
  >
    <template #sidebar>
      <h2 class="text-lg font-bold">Your registration</h2>
      <p class="mt-3 text-sm font-medium">
        Registration status: {{ registrationStatusLabel(registration.status) }}
      </p>
    </template>
  </EventDetailPage>
</template>
