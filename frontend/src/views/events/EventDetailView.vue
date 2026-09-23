<script setup>
import { computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import { STATUS_LABELS } from "@/features/events/dashboard";
import { useEventsStore } from "@/stores/events";

const route = useRoute();
const router = useRouter();
const eventsStore = useEventsStore();
const event = computed(() => eventsStore.events.find((storedEvent) => storedEvent.id === route.params.id));
const statusLabel = computed(() => STATUS_LABELS[event.value?.status] ?? event.value?.status.replaceAll("_", " "));

function displayDate(value, timeZone) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat("en-SG", {
    dateStyle: "full",
    timeZone,
  }).format(new Date(`${value}T12:00:00Z`));
}

function displayDateTime(date, time, timeZone) {
  if (!date || !time) return "Not provided";
  return `${displayDate(date, timeZone)} at ${time}`;
}

function displayValue(value) {
  return value || "Not provided";
}

onMounted(async () => {
  try {
    await eventsStore.get(route.params.id);
  } catch {
    return;
  }
});
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <div class="mb-8 flex flex-wrap items-center justify-between gap-4">
      <BauhausButton variant="outline" @click="router.push({ name: 'dashboard-organiser' })">Back to requests</BauhausButton>
      <p v-if="event" class="text-xs font-bold uppercase tracking-widest text-ink/70">Request {{ event.id }}</p>
    </div>

    <p
      v-if="eventsStore.error"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ eventsStore.error }}
    </p>

    <template v-if="event">
      <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-8">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event request</p>
            <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ event.name }}</h1>
          </div>
          <p class="border-2 border-ink bg-canvas px-3 py-2 text-xs font-black uppercase tracking-widest shadow-hard">
            {{ statusLabel }}
          </p>
        </div>
      </BauhausCard>

      <div class="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase tracking-tight">Request details</h2>
          <dl class="mt-6 grid gap-5 sm:grid-cols-2">
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Purpose</dt><dd class="mt-1 font-medium">{{ displayValue(event.purpose) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Expected attendance</dt><dd class="mt-1 font-medium">{{ displayValue(event.expectedAttendance) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Proposed date</dt><dd class="mt-1 font-medium">{{ displayDate(event.date, event.eventTimezone) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Time</dt><dd class="mt-1 font-medium">{{ displayValue(event.startTime) }}–{{ displayValue(event.endTime) }} ({{ event.eventTimezone }})</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Preferred layout</dt><dd class="mt-1 font-medium">{{ displayValue(event.layoutPreference) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Facilities</dt><dd class="mt-1 font-medium">{{ event.facilitiesRequired.length ? event.facilitiesRequired.join(", ") : "None specified" }}</dd></div>
            <div class="sm:col-span-2"><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Description</dt><dd class="mt-1 whitespace-pre-wrap font-medium">{{ displayValue(event.description) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Accessibility needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.accessibilityNeeds) }}</dd></div>
            <div><dt class="text-xs font-bold uppercase tracking-widest text-ink/70">Equipment needs</dt><dd class="mt-1 font-medium">{{ displayValue(event.preliminaryEquipmentNeeds) }}</dd></div>
          </dl>
        </BauhausCard>

        <aside class="flex flex-col gap-8">
          <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow">
            <h2 class="text-2xl font-black uppercase tracking-tight">Registration</h2>
            <p class="mt-4 text-sm font-bold uppercase tracking-wide">{{ event.registrationEnabled ? "Enabled" : "Not enabled" }}</p>
            <p class="mt-2 text-xs font-bold uppercase tracking-widest text-canvas/70">{{ event.eventTimezone }}</p>
            <dl v-if="event.registrationEnabled" class="mt-5 grid gap-4 text-sm">
              <div><dt class="font-bold uppercase tracking-widest text-canvas/70">Capacity</dt><dd class="mt-1 font-medium">{{ displayValue(event.registrationCapacity) }}</dd></div>
              <div><dt class="font-bold uppercase tracking-widest text-canvas/70">Opens</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.registrationOpensAt?.slice(0, 10), event.registrationOpensAt?.slice(11, 16), event.eventTimezone) }}</dd></div>
              <div><dt class="font-bold uppercase tracking-widest text-canvas/70">Closes</dt><dd class="mt-1 font-medium">{{ displayDateTime(event.registrationClosesAt?.slice(0, 10), event.registrationClosesAt?.slice(11, 16), event.eventTimezone) }}</dd></div>
            </dl>
          </BauhausCard>
          <BauhausCard background="white" accent="none">
            <h2 class="text-2xl font-black uppercase tracking-tight">Planning status</h2>
            <p class="mt-3 text-sm font-medium">Your request is currently <strong class="uppercase">{{ statusLabel }}</strong>.</p>
            <p class="mt-3 text-sm font-medium">Coordinator: {{ event.coordinatorId || "To be assigned" }}</p>
          </BauhausCard>
        </aside>
      </div>
    </template>
  </main>
</template>