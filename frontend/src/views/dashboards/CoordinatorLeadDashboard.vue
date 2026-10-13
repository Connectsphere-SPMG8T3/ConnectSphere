<script setup>
/**
 * Event Coordinator Lead dashboard — CR-101.
 *
 * AC1: the shared unassigned queue and the active events in this Lead's scope,
 *      each with its coordinator and status.
 * AC2: filter by coordinator and status; how many active events each coordinator has.
 * AC3: every event opens its Lead page, where it can be reassigned.
 * AC4: only active statuses are listed; the API never returns anything else.
 *
 * Everything comes from `GET /events/dashboard/lead`; the API decides which events
 * are in this Lead's scope (AC5), so nothing here filters by who assigned what.
 */
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import { STATUS_LABELS } from "@/features/events/dashboard";
import {
  LEAD_STATUS_OPTIONS,
  coordinatorFilterOptions,
  filterLeadEvents,
  sortLeadEvents,
} from "@/features/events/leadDashboard";
import { useLeadDashboardStore } from "@/features/events/leadDashboardStore";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const store = useLeadDashboardStore();

onMounted(() => store.load());

// Until the first load settles no figure can be stood behind.
const isLoaded = computed(() => store.hasSettled && !store.error);

const coordinator = ref("");
const status = ref([]);
const search = ref("");

const coordinatorOptionsForFilter = computed(() => coordinatorFilterOptions(store.coordinators));
const queue = computed(() => sortLeadEvents(store.unassigned));
const visibleActive = computed(() =>
  sortLeadEvents(
    filterLeadEvents(store.activeEvents, {
      coordinator: coordinator.value,
      status: status.value,
      search: search.value,
    }),
  ),
);

function clearFilters() {
  coordinator.value = "";
  status.value = [];
  search.value = "";
}

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

const leadRoute = (eventId) => ({ name: "lead-event", params: { id: eventId } });
const rowClasses =
  "block border-2 border-ink bg-canvas p-4 shadow-hard transition duration-150 hover:-translate-y-0.5 hover:bg-bauhaus-yellow/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink motion-reduce:transition-none sm:border-4 sm:p-5";
</script>

<template>
  <main class="py-12">
    <BauhausCard background="blue" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event Coordinator Lead Dashboard</p>
      <h1 class="mt-2 text-3xl font-black uppercase leading-none tracking-tighter sm:text-4xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-2xl text-sm font-medium">
        New requests waiting for a coordinator, and the active events you supervise.
      </p>
    </BauhausCard>

    <p
      v-if="store.error"
      role="alert"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ store.error }}
    </p>
    <p
      v-else-if="!store.hasSettled"
      role="status"
      class="mb-8 border-2 border-ink bg-canvas px-4 py-3 text-sm font-bold uppercase tracking-wide shadow-hard sm:border-4"
    >
      Loading events...
    </p>

    <template v-if="isLoaded">
      <div class="mb-10 grid grid-cols-1 gap-6 md:grid-cols-2">
        <BauhausSummaryCard
          label="Unassigned"
          :value="store.unassigned.length"
          detail="Requests waiting for a coordinator"
          background="red"
          accent="circle"
          accent-color="bauhaus-yellow"
        />
        <BauhausSummaryCard
          label="Active events"
          :value="store.activeEvents.length"
          detail="Assigned and not yet closed"
          background="yellow"
          accent="square"
          accent-color="bauhaus-red"
        />
      </div>

      <section v-if="store.coordinators.length" class="mb-10" aria-labelledby="coordinator-load">
        <h2 id="coordinator-load" class="mb-4 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
          Coordinator workload
        </h2>
        <ul data-testid="coordinator-counts" class="flex flex-wrap gap-3">
          <li
            v-for="person in store.coordinators"
            :key="person.id"
            class="flex items-baseline gap-3 border-2 border-ink bg-canvas px-4 py-2"
          >
            <span class="text-sm font-bold uppercase tracking-tight">{{ person.full_name }}</span>
            <span class="text-xl font-black tracking-tighter">{{ person.active_count }}</span>
          </li>
        </ul>
      </section>

      <section class="mb-10" data-testid="unassigned-queue" aria-labelledby="unassigned-heading">
        <div class="mb-5 flex items-baseline justify-between gap-4">
          <h2 id="unassigned-heading" class="text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
            Unassigned queue
          </h2>
          <span class="text-sm font-bold uppercase tracking-widest">{{ queue.length }} total</span>
        </div>
        <ul v-if="queue.length" class="grid gap-4">
          <li v-for="event in queue" :key="event.event_id">
            <RouterLink :to="leadRoute(event.event_id)" :data-lead-event="event.event_id" :class="rowClasses">
              <p class="text-lg font-black uppercase leading-tight tracking-tighter">{{ event.event_name }}</p>
              <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/70">
                {{ STATUS_LABELS[event.status] }} · {{ formatDate(event.starts_at) }}
                <template v-if="event.organiser_name"> · {{ event.organiser_name }}</template>
              </p>
            </RouterLink>
          </li>
        </ul>
        <BauhausEmptyState
          v-else
          title="Nothing waiting to be assigned"
          detail="New event requests appear here until you assign a coordinator."
        />
      </section>

      <section class="mb-10 border-4 border-ink bg-canvas p-5 shadow-hard" aria-labelledby="lead-filters">
        <h2 id="lead-filters" class="mb-5 text-2xl font-black uppercase tracking-tight">Find an event</h2>
        <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
          <BauhausInput
            v-model="search"
            class="w-full sm:min-w-0 sm:flex-[1.4_1_0%]"
            label="Event name"
            placeholder="Search by event name"
            aria-label="Search events"
            compact
          />
          <BauhausSelect
            v-model="coordinator"
            class="w-full sm:min-w-0 sm:flex-1"
            label="Coordinator"
            :options="coordinatorOptionsForFilter"
            aria-label="Filter events by coordinator"
            compact
          />
          <BauhausSelect
            v-model="status"
            class="w-full sm:min-w-0 sm:flex-1"
            label="Status"
            :options="LEAD_STATUS_OPTIONS"
            aria-label="Filter events by status"
            multiple
            compact
          />
          <BauhausButton class="h-[50px] px-4 py-2 text-xs shadow-none sm:border-2" variant="yellow" @click="clearFilters">
            Clear
          </BauhausButton>
        </div>
      </section>

      <section data-testid="active-events" aria-labelledby="active-heading">
        <div class="mb-5 flex items-baseline justify-between gap-4">
          <h2 id="active-heading" class="text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl">
            Active events
          </h2>
          <span class="text-sm font-bold uppercase tracking-widest">{{ visibleActive.length }} shown</span>
        </div>
        <ul v-if="visibleActive.length" class="grid gap-4">
          <li v-for="event in visibleActive" :key="event.event_id">
            <RouterLink :to="leadRoute(event.event_id)" :data-lead-event="event.event_id" :class="rowClasses">
              <p class="text-lg font-black uppercase leading-tight tracking-tighter">{{ event.event_name }}</p>
              <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/70">
                {{ STATUS_LABELS[event.status] }} · {{ formatDate(event.starts_at) }}
              </p>
              <p class="mt-2 text-sm font-medium">Coordinator: {{ event.coordinator?.full_name ?? "Unassigned" }}</p>
            </RouterLink>
          </li>
        </ul>
        <BauhausEmptyState
          v-else
          :title="store.activeEvents.length ? 'No matching events' : 'No active events'"
          :detail="
            store.activeEvents.length
              ? 'Clear or change the filters to see another event.'
              : 'Events you assign will appear here until they are completed, cancelled or rejected.'
          "
        />
      </section>
    </template>
  </main>
</template>
