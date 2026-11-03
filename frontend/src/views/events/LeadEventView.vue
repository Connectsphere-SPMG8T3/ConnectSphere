<script setup>
/**
 * An event as the Event Coordinator Lead sees it (CR-101 AC3): its basic
 * information, who coordinates it, and a reassign action. Reads from the Lead
 * dashboard store, so only events in this Lead's scope can be found here; the
 * API enforces the scope again on the reassign itself.
 */
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import CancellationReasonModal from "@/components/events/CancellationReasonModal.vue";
import EventStatusHistory from "@/components/events/EventStatusHistory.vue";
import { showToast } from "@/composables/useToast";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { coordinatorOptions } from "@/features/events/leadDashboard";
import { useLeadDashboardStore } from "@/features/events/leadDashboardStore";

const route = useRoute();
const router = useRouter();
const store = useLeadDashboardStore();

// Always start from a fresh load: rows left by an earlier visit (or another account on
// this tab) must never be shown, and the version sent on reassign must be current.
store.reset();
// The history is the event's own (SCRUM-81 AC4), so it loads beside the dashboard rather than
// after it: an event outside the Lead's scope shows no history card whatever the API answers.
onMounted(() => {
  store.load();
  store.loadHistory(route.params.id);
});

const event = computed(() => store.eventById(route.params.id));
const isLoaded = computed(() => store.hasSettled && !store.error);
const options = computed(() => coordinatorOptions(store.coordinators, event.value?.coordinator?.id));
const selected = ref("");
const isConfirming = ref(false);
// CR-106: declining the coordinator's request to be reassigned, with the Lead's reason.
const isDeclining = ref(false);
// An event with no coordinator is being assigned, so the page says so. A `submitted` one goes
// through assign (SCRUM-12); an older event that is active but never got a coordinator can only
// be taken by reassign (CR-101). One that already has a coordinator is reassigned.
const isQueued = computed(() => !event.value?.coordinator);
const usesAssign = computed(() => event.value?.status === "submitted" && isQueued.value);
const selectedName = computed(() => options.value.find((option) => option.value === selected.value)?.label ?? "");

// Times are stored in UTC and shown in Asia/Singapore (REQUIREMENTS §4).
const dateFormat = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

function formatDate(value) {
  if (!value) return "Date to be confirmed";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Date to be confirmed" : dateFormat.format(parsed);
}

async function decline(reason) {
  const eventName = event.value.event_name;
  if (await store.declineReassignment(route.params.id, reason)) {
    isDeclining.value = false;
    showToast(`Reassignment request for "${eventName}" declined.`);
  }
}

async function reassign() {
  isConfirming.value = false;
  const eventName = event.value.event_name;
  const coordinatorName = selectedName.value;
  const queued = isQueued.value;
  const ok = usesAssign.value
    ? await store.assign(route.params.id, selected.value)
    : await store.reassign(route.params.id, selected.value, event.value.version);
  if (ok) {
    showToast(`"${eventName}" ${queued ? "assigned" : "reassigned"} to ${coordinatorName}.`);
    router.push({ name: "dashboard-coordinator-lead" });
  }
}
</script>

<template>
  <main class="py-8">
    <p class="mb-6">
      <RouterLink
        :to="{ name: 'dashboard-coordinator-lead' }"
        class="text-xs font-bold underline decoration-2 underline-offset-4"
      >
        Back to dashboard
      </RouterLink>
    </p>

    <p
      v-if="store.error"
      role="alert"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ store.error }}
    </p>
    <p
      v-else-if="!store.hasSettled"
      role="status"
      class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-bold shadow-hard sm:border-4"
    >
      Loading event...
    </p>

    <template v-if="isLoaded">
      <BauhausEmptyState
        v-if="!event"
        title="This event isn't in your scope"
        detail="It may have been assigned by another Lead, or it is no longer active."
      />

      <template v-else>
        <BauhausCard background="yellow" accent="none" class="mb-8">
          <p class="text-xs font-bold text-ink/70">
            {{ STATUS_LABELS[event.status] }}
          </p>
          <h1 class="mt-2 text-3xl font-bold leading-tight sm:text-4xl">
            {{ event.event_name }}
          </h1>
          <dl class="mt-5 grid gap-4 text-sm font-medium sm:grid-cols-2">
            <div>
              <dt class="text-xs font-bold text-ink/70">Date</dt>
              <dd>{{ formatDate(event.starts_at) }}</dd>
            </div>
            <div>
              <dt class="text-xs font-bold text-ink/70">Organiser</dt>
              <dd>{{ event.organiser_name ?? "Unknown" }}</dd>
            </div>
            <div>
              <dt class="text-xs font-bold text-ink/70">Coordinator</dt>
              <dd>{{ event.coordinator?.full_name ?? "Unassigned" }}</dd>
            </div>
            <div v-if="event.expected_attendance != null">
              <dt class="text-xs font-bold text-ink/70">Expected attendance</dt>
              <dd>{{ event.expected_attendance }}</dd>
            </div>
            <div v-if="event.purpose" class="sm:col-span-2">
              <dt class="text-xs font-bold text-ink/70">Purpose</dt>
              <dd>{{ event.purpose }}</dd>
            </div>
          </dl>
        </BauhausCard>

        <!-- CR-106 AC2: the coordinator asked to be moved. Reassigning below answers it; declining needs a reason. -->
        <section
          v-if="event.open_reassignment_request"
          data-testid="reassignment-request-banner"
          class="mb-8 border-4 border-ink bg-bauhaus-yellow p-6 shadow-hard sm:p-8"
        >
          <h2 class="text-2xl font-bold">
            {{ event.open_reassignment_request.requested_by?.full_name ?? "The coordinator" }} asked to be reassigned
          </h2>
          <p class="mt-4 text-sm font-bold">Reason:</p>
          <p class="mt-1 whitespace-pre-wrap font-medium" data-testid="reassignment-request-reason">{{ event.open_reassignment_request.reason }}</p>
          <p class="mt-4 text-sm font-bold">They stay assigned until you reassign the event or decline.</p>
          <div class="mt-6">
            <BauhausButton
              size="sm"
              variant="outline"
              aria-label="Decline request"
              :disabled="store.isDeclining"
              @click="store.declineError = null; isDeclining = true"
            >
              Decline request
            </BauhausButton>
          </div>
        </section>

        <section class="border-4 border-ink bg-canvas p-5 shadow-hard" aria-labelledby="reassign-heading">
          <h2 id="reassign-heading" class="text-2xl font-bold">
            {{ isQueued ? "Assign" : "Reassign" }} coordinator
          </h2>
          <p
            v-if="store.reassignError"
            role="alert"
            class="mt-4 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas"
          >
            {{ store.reassignError }}
          </p>
          <div class="mt-5 flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
            <BauhausSelect
              v-model="selected"
              class="w-full sm:flex-1"
              label="Coordinator"
              :options="options"
              placeholder="Choose a coordinator"
              aria-label="Choose a coordinator"
              compact
            />
            <BauhausButton
              class="h-[50px] shrink-0"
              variant="primary"
              aria-label="Reassign event"
              :disabled="!selected || store.isReassigning"
              @click="isConfirming = true"
            >
              {{ isQueued ? "Assign" : "Reassign" }}
            </BauhausButton>
          </div>
        </section>

        <!-- SCRUM-81 AC4: who moved this event from whom to whom, and when. Reassignments only. -->
        <section
          class="mt-8 border-4 border-ink bg-canvas p-5 shadow-hard"
          aria-labelledby="reassignment-history-heading"
          data-testid="reassignment-history"
        >
          <h2 id="reassignment-history-heading" class="mb-4 text-2xl font-bold">Reassignment history</h2>
          <p v-if="store.historyError" class="text-sm font-bold" data-testid="reassignment-history-error">
            {{ store.historyError }}
          </p>
          <p v-else-if="store.isLoadingHistory" class="text-sm font-medium text-ink/70">Loading history...</p>
          <EventStatusHistory v-else :entries="store.history" empty-text="No reassignments yet." />
        </section>
      </template>
    </template>

    <CancellationReasonModal
      :open="isDeclining"
      title="Decline the reassignment request?"
      :message="`${event?.coordinator?.full_name ?? 'The coordinator'} stays assigned to ${event?.event_name ?? 'this event'} and is told your reason.`"
      confirm-label="Decline request"
      confirm-aria-label="Confirm decline reassignment request"
      :busy="store.isDeclining"
      :error="isDeclining ? store.declineError : null"
      @confirm="decline"
      @cancel="isDeclining = false"
    />
    <ConfirmModal
      :open="isConfirming"
      :title="isQueued ? 'Assign event?' : 'Reassign event?'"
      :message="`${event?.event_name ?? 'This event'} will be coordinated by ${selectedName}. ${isQueued ? 'They and the organiser are notified.' : 'They, the organiser and any previous coordinator are notified.'}`"
      :confirm-label="isQueued ? 'Assign' : 'Reassign'"
      cancel-label="Cancel"
      @confirm="reassign"
      @stay="isConfirming = false"
    />
  </main>
</template>
