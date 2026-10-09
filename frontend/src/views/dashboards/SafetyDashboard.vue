<script setup>
import { computed, onMounted } from "vue";
import { RouterLink } from "vue-router";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausSummaryCard from "@/components/common/BauhausSummaryCard.vue";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";
import { displaySafetyTime } from "@/features/events/safetyDecision";
import { outcomeCounts, queueSummary } from "@/features/events/safetyDashboard";
import { useSafetyDecisionStore } from "@/features/events/safetyDecisionStore";

const safety = useSafetyDecisionStore();
const summary = computed(() => queueSummary(safety.queue));
const outcomes = computed(() => outcomeCounts(safety.history));

onMounted(() => {
  safety.loadQueue();
  safety.loadHistory();
});
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="red" accent="none" class="mb-8">
      <p class="text-xs font-bold uppercase tracking-widest">Safety Officer Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">Safety review queue</h1>
    </BauhausCard>

    <!-- CR-103 AC7: figures counted from the loaded queue and the 30-day history. -->
    <div class="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
      <BauhausSummaryCard label="In queue" :value="summary.waiting" detail="Waiting for a safety check" background="yellow" accent="circle" />
      <BauhausSummaryCard label="Oldest waiting" :value="summary.oldestWaitLabel" detail="Since it was sent for review" background="white" accent="none" />
    </div>
    <div class="mb-10 grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
      <BauhausSummaryCard label="Approved" :value="outcomes.approved" detail="Last 30 days" background="white" accent="none" />
      <BauhausSummaryCard label="Changes requested" :value="outcomes.changesRequested" detail="Last 30 days" background="white" accent="none" />
      <BauhausSummaryCard label="Arrangement rejected" :value="outcomes.arrangementRejected" detail="Last 30 days" background="white" accent="none" />
    </div>

    <h2 class="mb-4 text-2xl font-black uppercase tracking-tighter">Waiting for review</h2>
    <p v-if="safety.loading" class="font-bold uppercase">Loading safety queue…</p>
    <p v-else-if="safety.error" role="alert" class="border-4 border-ink p-4 font-bold">{{ safety.error }}</p>
    <BauhausEmptyState v-else-if="!safety.queue.length" title="No events are waiting for a safety check." />
    <div v-else class="grid gap-6">
      <BauhausCard v-for="item in safety.queue" :key="item.event_id" background="white" accent="none">
        <h3 class="break-words text-2xl font-black uppercase">
          <RouterLink :to="{ name: 'safety-review', params: { id: item.event_id } }" class="underline decoration-2 underline-offset-4">{{ item.name }}</RouterLink>
        </h3>
        <dl class="mt-4 grid gap-4 sm:grid-cols-2">
          <div><dt class="font-bold uppercase">Organiser</dt><dd>{{ item.organiser_name }}</dd></div>
          <div><dt class="font-bold uppercase">Starts</dt><dd>{{ displaySafetyTime(item.starts_at) }}</dd></div>
          <div><dt class="font-bold uppercase">Expected attendance</dt><dd>{{ item.expected_attendance ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold uppercase">Waiting since</dt><dd>{{ displaySafetyTime(item.entered_review_at) }}</dd></div>
        </dl>
      </BauhausCard>
    </div>

    <h2 class="mb-4 mt-12 text-2xl font-black uppercase tracking-tighter">Recent decisions</h2>
    <p v-if="safety.historyError" role="alert" class="border-4 border-ink p-4 font-bold">{{ safety.historyError }}</p>
    <BauhausEmptyState v-else-if="!safety.history.length" title="No safety decisions in the last 30 days." />
    <div v-else class="grid gap-4">
      <BauhausCard v-for="item in safety.history" :key="item.id" data-history-item background="white" accent="none">
        <p class="break-words text-xl font-black uppercase">{{ item.event_name }}</p>
        <SafetyDecisionDetails :decision="item" class="mt-2" />
      </BauhausCard>
    </div>
  </main>
</template>
