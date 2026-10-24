<script setup>
import { RouterLink } from "vue-router";

import BrandMark from "@/components/common/BrandMark.vue";

const year = new Date().getFullYear();

// One column per audience, so attendees and organisers each find their way in.
const columns = [
  {
    heading: "Attendees",
    links: [
      { label: "Browse events", to: "/" },
      { label: "Create attendee account", to: { name: "signup", params: { role: "attendee" } } },
    ],
  },
  {
    heading: "Organisers",
    links: [
      { label: "Create organiser account", to: { name: "signup", params: { role: "organiser" } } },
      { label: "Sign in", to: "/login" },
    ],
  },
];
</script>

<template>
  <!-- The signed-out pages' footer, the counterpart of PublicHeader. Render it
       after the page's <main>; its top border closes off whatever is above it. -->
  <footer class="border-t-4 border-ink bg-canvas px-5 text-ink sm:px-10">
    <div class="mx-auto flex max-w-6xl flex-col gap-8 py-10 md:flex-row md:justify-between">
      <div class="max-w-xs">
        <RouterLink to="/" class="flex items-center gap-3" aria-label="ConnectSphere events">
          <BrandMark />
          <span class="text-lg font-bold leading-tight">ConnectSphere</span>
        </RouterLink>
        <p class="mt-4 text-sm font-medium">Event planning and venue booking in Singapore.</p>
      </div>
      <nav class="grid grid-cols-2 gap-8 sm:gap-16" aria-label="Footer">
        <div v-for="column in columns" :key="column.heading">
          <h2 class="text-sm font-bold">{{ column.heading }}</h2>
          <ul class="mt-4 flex flex-col gap-3">
            <li v-for="link in column.links" :key="link.label">
              <RouterLink :to="link.to" class="-mx-1 px-1 text-sm font-medium hover:bg-muted">{{ link.label }}</RouterLink>
            </li>
          </ul>
        </div>
      </nav>
    </div>
    <div class="mx-auto max-w-6xl border-t-2 border-ink py-5">
      <p class="text-xs font-medium">© {{ year }} ConnectSphere</p>
    </div>
  </footer>
</template>
