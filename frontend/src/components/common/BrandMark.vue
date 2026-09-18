<script setup>
// The ConnectSphere mark: the three Bauhaus primitives stacked in a square.
// Shared by the sidebar brand and, on small screens where the sidebar is a
// drawer, by the top bar — so the logo is on screen either way.
</script>

<template>
  <span class="relative block h-9 w-9 shrink-0" aria-hidden="true">
    <span class="absolute left-0 top-0 h-5 w-5 rounded-full bg-bauhaus-red"></span>
    <span class="absolute right-0 top-0 h-5 w-5 bg-bauhaus-blue"></span>
    <span
      class="absolute bottom-0 left-1/2 h-0 w-0 -translate-x-1/2 border-b-[18px] border-l-[10px] border-r-[10px] border-b-bauhaus-yellow border-l-transparent border-r-transparent"
    ></span>
  </span>
</template>
