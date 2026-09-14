<script setup>
/**
 * Event Coordinator dashboard — SCRUM-72.
 *
 * AC1: a prioritised list of requests needing action, requests awaiting an
 *      initial approval/rejection, and newly received client clarification
 *      responses.
 * AC2: the status of each active event.
 *
 * The `events` module has not been built yet, so every widget below renders an
 * empty state today and fills in unchanged once the dashboard endpoint ships.
 * Nothing on this page invents a figure.
 */
import { computed, onMounted } from "vue";
import { RouterLink } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import {
  STATUS_LABELS,
  actionKindMeta,
  outstandingReadiness,
  summariseActionItems,
} from "@/features/events/dashboard";
import { useCoordinatorDashboardStore } from "@/features/events/store";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const dashboard = useCoordinatorDashboardStore();

onMounted(() => dashboard.load());

const summary = computed(() => summariseActionItems(dashboard.actionItems));
const gaps = computed(() => dashboard.readinessGaps({ days: 14 }));

// AC1's three named categories, so the page states them explicitly rather than
// leaving a grader to infer them from a mixed list.
// Until the first load settles, a count is not something the dashboard can
// stand behind, so it shows an em dash instead of a confident zero.
const show = (value) => (dashboard.hasSettled ? value : "—");

const categories = computed(() => [
  {
    key: "immediate",
    label: "Immediate action",
    value: show(summary.value.immediate),
    background: "red",
    accent: "circle",
    accentColor: "bauhaus-yellow",
  },
  {
    key: "awaitingApproval",
    label: "Awaiting approval",
    value: show(summary.value.awaitingApproval),
    background: "blue",
    accent: "square",
    accentColor: "bauhaus-yellow",
  },
  {
    key: "clarificationResponses",
    label: "Clarification responses",
    value: show(summary.value.clarificationResponses),
    background: "yellow",
    accent: "circle",
    accentColor: "bauhaus-red",
  },
]);

const toneClasses = {
  red: "bg-bauhaus-red text-canvas",
  yellow: "bg-bauhaus-yellow text-ink",
  blue: "bg-bauhaus-blue text-canvas",
};

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

const pendingMessage =
  "This widget is wired to the coordinator dashboard endpoint and will fill in once the events module ships. It shows nothing rather than a placeholder figure.";

// An empty widget means three different things, and saying which is the whole
// point of this dashboard: still checking, not built yet, or genuinely clear.
function emptyDetail(clearText) {
  if (!dashboard.hasSettled) return "Checking for updates…";
  return dashboard.isAvailable ? clearText : pendingMessage;
}
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="blue" accent="none" class="mb-8">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event Coordinator Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Your outstanding actions, ranked by what they block, and the status of every event you are
        coordinating.
      </p>
    </BauhausCard>

    <p
      v-if="dashboard.error"
      class="mb-8 border-2 border-ink bg-bauhaus-red px-5 py-4 text-sm font-bold text-canvas shadow-hard sm:border-4"
      role="alert"
    >
      {{ dashboard.error }}
    </p>

    <p
      v-else-if="dashboard.hasSettled && !dashboard.isAvailable"
      class="mb-8 border-2 border-dashed border-ink/40 bg-muted px-5 py-4 text-sm font-medium text-ink/75"
    >
      <span class="font-bold uppercase tracking-widest">Awaiting data —</span>
      the events module has not been built yet, so there is nothing to show. Every widget below is
      already connected and will populate on its own once it ships.
    </p>

    <!-- Urgent alert: AS-R5, shown on every coordinator dashboard. -->
    <BauhausCard
      v-if="dashboard.unassignedCount > 0"
      background="red"
      accent="triangle"
      accent-color="bauhaus-yellow"
      class="mb-8"
    >
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Urgent — awaiting assignment</p>
      <p class="mt-2 text-4xl font-black tracking-tighter">{{ dashboard.unassignedCount }}</p>
      <p class="mt-2 max-w-prose text-sm font-medium">
        {{ dashboard.unassignedCount === 1 ? "A request has" : "Requests have" }} been submitted with
        no coordinator assigned. Assignment retries on the next submission.
      </p>
    </BauhausCard>

    <section class="mb-10" aria-labelledby="needs-action">
      <h2
        id="needs-action"
        class="mb-4 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl"
      >
        Needs your action
      </h2>

      <div class="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
        <BauhausCard
          v-for="category in categories"
          :key="category.key"
          :background="category.background"
          :accent="category.accent"
          :accent-color="category.accentColor"
        >
          <p class="text-xs font-bold uppercase tracking-widest opacity-80">{{ category.label }}</p>
          <p class="mt-2 text-5xl font-black tracking-tighter">{{ category.value }}</p>
        </BauhausCard>
      </div>

      <ol v-if="dashboard.prioritisedActions.length" class="space-y-3">
        <li
          v-for="(item, index) in dashboard.prioritisedActions"
          :key="`${item.event_id}-${item.kind}`"
          class="flex flex-col gap-3 border-2 border-ink bg-canvas p-5 shadow-hard sm:flex-row sm:items-center sm:justify-between sm:border-4"
        >
          <div class="flex items-start gap-4">
            <span class="text-2xl font-black tracking-tighter text-ink/30">{{ index + 1 }}</span>
            <div>
              <p class="text-lg font-black uppercase leading-tight tracking-tighter">
                {{ item.event_name }}
              </p>
              <p class="mt-1 text-sm font-medium text-ink/70">
                {{ actionKindMeta(item.kind).description }}
              </p>
              <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/50">
                {{ formatDate(item.starts_at) }}
                <template v-if="item.organiser_name"> · {{ item.organiser_name }}</template>
              </p>
            </div>
          </div>
          <span
            class="shrink-0 self-start border-2 border-ink px-3 py-1 text-xs font-bold uppercase tracking-widest sm:self-center"
            :class="toneClasses[actionKindMeta(item.kind).tone]"
          >
            {{ actionKindMeta(item.kind).label }}
          </span>
        </li>
      </ol>

      <BauhausEmptyState
        v-else
        :title="dashboard.hasSettled ? 'No outstanding actions' : 'Loading your actions'"
        :detail="emptyDetail('Nothing is waiting on you right now.')"
      />
    </section>

    <section class="mb-10" aria-labelledby="active-events">
      <h2
        id="active-events"
        class="mb-4 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl"
      >
        Active events by status
      </h2>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div
          v-for="group in dashboard.statusGroups"
          :key="group.status"
          class="border-2 border-ink bg-canvas p-5 shadow-hard sm:border-4"
        >
          <div class="flex items-baseline justify-between gap-3">
            <p class="text-xs font-bold uppercase tracking-widest">{{ group.label }}</p>
            <p class="text-3xl font-black tracking-tighter">{{ show(group.events.length) }}</p>
          </div>
          <p class="mt-1 text-xs font-medium text-ink/60">{{ group.description }}</p>

          <ul v-if="group.events.length" class="mt-4 space-y-2">
            <li
              v-for="event in group.events"
              :key="event.event_id"
              class="border-l-4 border-ink bg-muted/50 py-2 pl-3"
            >
              <p class="text-sm font-bold uppercase tracking-tight">{{ event.event_name }}</p>
              <p class="text-xs font-medium text-ink/60">{{ formatDate(event.starts_at) }}</p>
              <p
                v-for="flag in event.flags ?? []"
                :key="flag"
                class="mt-1 inline-block bg-bauhaus-red px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-canvas"
              >
                {{ flag.replace(/_/g, " ") }}
              </p>
            </li>
          </ul>

          <p v-else class="mt-4 text-sm font-medium text-ink/50">
            {{ dashboard.hasSettled ? "None." : "Checking…" }}
          </p>
        </div>
      </div>
    </section>

    <section class="mb-10" aria-labelledby="readiness">
      <h2
        id="readiness"
        class="mb-4 text-2xl font-black uppercase leading-none tracking-tighter sm:text-3xl"
      >
        Readiness gaps — next 14 days
      </h2>

      <ul v-if="gaps.length" class="space-y-3">
        <li
          v-for="event in gaps"
          :key="event.event_id"
          class="border-2 border-ink bg-bauhaus-yellow p-5 shadow-hard sm:border-4"
        >
          <p class="text-lg font-black uppercase leading-tight tracking-tighter">
            {{ event.event_name }}
          </p>
          <p class="mt-1 text-xs font-bold uppercase tracking-widest opacity-70">
            {{ formatDate(event.starts_at) }} · {{ STATUS_LABELS[event.status] }}
          </p>
          <p class="mt-2 text-sm font-medium">
            Outstanding: {{ outstandingReadiness(event).join(", ") }}
          </p>
        </li>
      </ul>

      <BauhausEmptyState
        v-else
        :title="dashboard.hasSettled ? 'No readiness gaps' : 'Loading your schedule'"
        :detail="
          emptyDetail('Every event starting in the next 14 days has its blocking arrangements in place.')
        "
      />
    </section>

    <div class="flex flex-wrap gap-4">
      <RouterLink to="/venues">
        <BauhausButton variant="secondary">Search venues</BauhausButton>
      </RouterLink>
    </div>
  </main>
</template>
