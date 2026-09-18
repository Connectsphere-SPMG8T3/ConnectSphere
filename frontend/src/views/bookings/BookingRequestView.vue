<script setup>
/**
 * Booking request details — a deliberate placeholder (SCRUM-70 AC5).
 *
 * The dashboard's pending-request rows have to lead somewhere, but the request
 * detail view and the approve/reject decision are SCRUM-19/20 and have neither
 * an endpoint nor a design yet. Rather than invent the page, this states what
 * is missing and which story brings it. The route and the link are real, so
 * SCRUM-19 fills this in without touching the dashboard.
 */
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";

const route = useRoute();

// Echoed back so the user can confirm the row they clicked is the row they got.
const shortId = computed(() => String(route.params.id ?? "").slice(0, 8).toUpperCase());
</script>

<template>
  <main class="py-12">
    <RouterLink
      :to="{ name: 'dashboard-venue-staff' }"
      class="mb-8 inline-block text-xs font-bold uppercase tracking-widest underline decoration-2 underline-offset-4"
    >
      ← Back to dashboard
    </RouterLink>

    <h1 class="mb-6 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
      Booking request {{ shortId }}
    </h1>

    <BauhausEmptyState
      title="Not built yet"
      detail="The full request — event timing, expected attendance, layout, facilities, and the approve or reject decision — arrives with SCRUM-19 and SCRUM-20 (REQUIREMENTS §6.12–6.13). Nothing is being withheld from you here; the page does not exist yet."
    />

    <div class="mt-8">
      <RouterLink :to="{ name: 'dashboard-venue-staff' }">
        <BauhausButton variant="secondary">Back to dashboard</BauhausButton>
      </RouterLink>
    </div>
  </main>
</template>
