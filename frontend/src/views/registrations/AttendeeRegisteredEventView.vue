<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import EventDetailPage from "@/components/registrations/EventDetailPage.vue";
import { showToast } from "@/composables/useToast";
import { canWithdrawRegistration, registrationStatusLabel } from "@/features/registrations/registeredEvents";
import { useRegistrationStore } from "@/features/registrations/store";

const route = useRoute();
const router = useRouter();
const registrationStore = useRegistrationStore();
const isWithdrawalConfirmationOpen = ref(false);
const withdrawalError = ref("");
const registration = computed(() =>
  registrationStore.myRegistrations.find(({ event }) => event.id === route.params.id),
);
const event = computed(() => registration.value?.event ?? null);
const breadcrumbItems = computed(() => [
  { label: "Dashboard", to: { name: "dashboard-attendee" } },
  { label: "My events", to: { name: "dashboard-attendee", query: { tab: "events" } } },
  { label: event.value?.name ?? "Event" },
]);
const canWithdraw = computed(() => canWithdrawRegistration(registration.value));

onMounted(() => {
  registrationStore.registrationActionError = null;
  registrationStore.loadMyRegistrations().catch(() => {});
});

async function withdrawRegistration() {
  if (!registration.value || !canWithdrawRegistration(registration.value) || registrationStore.isWithdrawing) return;
  withdrawalError.value = "";
  try {
    await registrationStore.withdraw(registration.value.event.id);
    isWithdrawalConfirmationOpen.value = false;
    showToast("Registration withdrawn");
    await router.replace({ name: "dashboard-attendee", query: { tab: "events" } });
  } catch (error) {
    withdrawalError.value = error.message || "Registration could not be withdrawn.";
  }
}

async function acceptInvitation() {
  try {
    await registrationStore.acceptInvitation(registration.value.id);
    showToast("You are registered for this event.");
  } catch {
    return;
  }
}

async function leaveWaitlist() {
  const wasInvited = registration.value.status === "invited";
  try {
    await registrationStore.leaveWaitlist(registration.value.id);
    showToast(wasInvited ? "You declined the invitation." : "You left the waitlist.");
    await router.push({ name: "dashboard-attendee", query: { tab: "events" } });
  } catch {
    return;
  }
}
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
    :breadcrumb-items="breadcrumbItems"
  >
    <template #sidebar>
      <h2 class="text-lg font-bold">Your registration</h2>
      <p class="mt-3 text-sm font-medium">
        Registration status: {{ registrationStatusLabel(registration.status) }}
      </p>
      <p v-if="withdrawalError" role="alert" class="mt-4 text-sm font-bold text-bauhaus-red">
        {{ withdrawalError }}
      </p>
      <BauhausButton
        v-if="canWithdraw"
        type="button"
        variant="outline"
        class="mt-5 w-full"
        :disabled="registrationStore.isWithdrawing"
        @click="isWithdrawalConfirmationOpen = true"
      >Withdraw registration</BauhausButton>
      <p v-if="registration.status === 'invited' && registration.invitation_expires_at" class="mt-3 text-sm font-medium">
        Accept by {{ new Intl.DateTimeFormat("en-SG", {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: event.event_timezone,
        }).format(new Date(registration.invitation_expires_at)) }}.
      </p>
      <p v-if="registrationStore.registrationActionError" role="alert" class="mt-4 text-sm font-bold">
        {{ registrationStore.registrationActionError }}
      </p>
      <BauhausButton
        v-if="registration.status === 'invited'"
        class="mt-5 w-full"
        variant="primary"
        :disabled="registrationStore.isUpdatingRegistration"
        @click="acceptInvitation"
      >
        {{ registrationStore.isUpdatingRegistration ? "Accepting…" : "Accept invitation" }}
      </BauhausButton>
      <BauhausButton
        v-if="registration.status === 'invited'"
        class="mt-3 w-full"
        variant="secondary"
        :disabled="registrationStore.isUpdatingRegistration"
        @click="leaveWaitlist"
      >
        {{ registrationStore.isUpdatingRegistration ? "Declining…" : "Decline invitation" }}
      </BauhausButton>
      <BauhausButton
        v-else-if="registration.status === 'waitlisted'"
        class="mt-5 w-full"
        variant="secondary"
        :disabled="registrationStore.isUpdatingRegistration"
        @click="leaveWaitlist"
      >
        {{ registrationStore.isUpdatingRegistration ? "Leaving…" : "Leave waitlist" }}
      </BauhausButton>
    </template>
  </EventDetailPage>
  <ConfirmModal
    :open="isWithdrawalConfirmationOpen"
    title="Withdraw from this event?"
    message="Your registration will be withdrawn and your place made available."
    confirm-label="Confirm withdrawal"
    cancel-label="Keep registration"
    @confirm="withdrawRegistration"
    @stay="isWithdrawalConfirmationOpen = false"
  />
</template>
