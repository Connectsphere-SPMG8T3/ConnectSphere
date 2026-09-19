<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";

const authStore = useAuthStore();
const eventsStore = useEventsStore();
const router = useRouter();

onMounted(() => eventsStore.load());
</script>

<template>
  <main class="py-12">
    <BauhausCard background="yellow" accent="none" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Event Organiser Dashboard</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        Welcome, {{ authStore.profile?.full_name }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Track your event requests, liaise with your coordinator, and monitor progress toward launch —
        all from one place.
      </p>
      <BauhausButton class="mt-6" variant="primary" @click="router.push({ name: 'event-new' })">New event request</BauhausButton>
    </BauhausCard>

    <div class="grid grid-cols-1 gap-6 sm:grid-cols-3">
      <BauhausCard background="red" accent="circle" accent-color="bauhaus-yellow">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">Drafts</p>
        <p class="mt-2 text-5xl font-black tracking-tighter">{{ eventsStore.drafts.length }}</p>
      </BauhausCard>
      <BauhausCard background="white" accent="square" accent-color="bauhaus-blue">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">Requests in progress</p>
        <p class="mt-2 text-5xl font-black tracking-tighter">{{ eventsStore.requests.length }}</p>
      </BauhausCard>
      <BauhausCard background="blue" accent="triangle" accent-color="bauhaus-yellow">
        <p class="text-xs font-bold uppercase tracking-widest opacity-80">Under review</p>
        <p class="mt-2 text-5xl font-black tracking-tighter">{{ eventsStore.events.filter((event) => event.status === 'under_review').length }}</p>
      </BauhausCard>
    </div>

    <p v-if="eventsStore.error" role="alert" class="mt-8 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4">{{ eventsStore.error }}</p>

    <section class="mt-10">
      <div class="mb-5 flex items-center justify-between gap-4">
        <h2 class="text-2xl font-black uppercase tracking-tight">Your requests</h2>
        <BauhausButton variant="outline" @click="router.push({ name: 'event-new' })">Create</BauhausButton>
      </div>
      <div v-if="eventsStore.events.length" class="grid gap-4">
        <BauhausCard v-for="event in eventsStore.events" :key="event.id" background="white" accent="none" class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h3 class="text-xl font-black uppercase tracking-tight">{{ event.name }}</h3>
            <p class="mt-1 text-xs font-bold uppercase tracking-widest text-ink/70">{{ event.status.replace('_', ' ') }}</p>
          </div>
          <BauhausButton v-if="event.status === 'draft'" variant="outline" @click="router.push({ name: 'event-new', query: { id: event.id } })">Continue draft</BauhausButton>
          <BauhausButton v-else variant="outline" @click="router.push({ name: 'event-detail', params: { id: event.id } })">View request</BauhausButton>
        </BauhausCard>
      </div>
      <p v-else class="border-2 border-ink bg-canvas px-4 py-6 text-sm font-medium shadow-hard sm:border-4">No event requests yet. Start with a draft when you are ready.</p>
    </section>
  </main>
</template>
