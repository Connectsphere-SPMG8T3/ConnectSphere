<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";

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
const canWithdraw = computed(() => canWithdrawRegistration(registration.value));

onMounted(() => registrationStore.loadMyRegistrations().catch(() => {}));

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
