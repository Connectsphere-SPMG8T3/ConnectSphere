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
onMounted(() => store.load());

const event = computed(() => store.eventById(route.params.id));
const isLoaded = computed(() => store.hasSettled && !store.error);
const options = computed(() => coordinatorOptions(store.coordinators, event.value?.coordinator?.id));
const selected = ref("");
const isConfirming = ref(false);
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
  <main class="py-12">
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
      </template>
    </template>

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
