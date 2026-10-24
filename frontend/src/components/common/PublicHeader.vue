<script setup>
import { RouterLink } from "vue-router";

import BrandMark from "@/components/common/BrandMark.vue";
</script>

<template>
  <!-- The signed-out pages' top bar. It sits outside the page's <main> so it
       starts flush with the top of the window, and its content width matches
       the landing page's hero so the brand lines up with the headline. -->
  <header class="sticky top-0 z-30 border-b-4 border-ink bg-canvas px-5 sm:px-10">
    <div class="mx-auto flex min-h-20 max-w-6xl items-center justify-between gap-4 py-4">
      <RouterLink to="/" class="flex items-center gap-3" aria-label="ConnectSphere events">
        <BrandMark />
        <!-- Below 380px the wordmark and both actions don't fit, so the mark
             stands alone, as it does in the signed-in top bar on phones. -->
        <span class="hidden text-lg font-bold leading-tight min-[380px]:inline">ConnectSphere</span>
      </RouterLink>
      <div class="flex shrink-0 items-center gap-3 whitespace-nowrap">
        <slot />
      </div>
    </div>
  </header>
</template>
