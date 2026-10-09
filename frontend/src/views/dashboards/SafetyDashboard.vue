<script setup>
import { onMounted } from "vue";
import { RouterLink } from "vue-router";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { displaySafetyTime } from "@/features/events/safetyDecision";
import { useSafetyDecisionStore } from "@/features/events/safetyDecisionStore";

const safety = useSafetyDecisionStore();

onMounted(() => safety.loadQueue());
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="red" accent="none" class="mb-8">
      <p class="text-xs font-bold uppercase tracking-widest">Safety Officer Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">Safety review queue</h1>
    </BauhausCard>
    <p v-if="safety.loading" class="font-bold uppercase">Loading safety queue…</p>
    <p v-else-if="safety.error" role="alert" class="border-4 border-ink p-4 font-bold">{{ safety.error }}</p>
    <BauhausEmptyState v-else-if="!safety.queue.length" title="No events are waiting for a safety check." />
    <div v-else class="grid gap-6">
      <BauhausCard v-for="item in safety.queue" :key="item.event_id" background="white" accent="none">
        <h2 class="break-words text-2xl font-black uppercase">
          <RouterLink :to="{ name: 'safety-review', params: { id: item.event_id } }" class="underline decoration-2 underline-offset-4">{{ item.name }}</RouterLink>
        </h2>
        <dl class="mt-4 grid gap-4 sm:grid-cols-2">
          <div><dt class="font-bold uppercase">Organiser</dt><dd>{{ item.organiser_name }}</dd></div>
          <div><dt class="font-bold uppercase">Starts</dt><dd>{{ displaySafetyTime(item.starts_at) }}</dd></div>
          <div><dt class="font-bold uppercase">Expected attendance</dt><dd>{{ item.expected_attendance ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold uppercase">Waiting since</dt><dd>{{ displaySafetyTime(item.entered_review_at) }}</dd></div>
        </dl>
      </BauhausCard>
    </div>
  </main>
</template>
