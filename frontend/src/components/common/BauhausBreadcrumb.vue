<script setup>
import { RouterLink } from "vue-router";

// A breadcrumb trail for a page inside a section: every item but the last links
// to its page, and the last item names the page being viewed. A trail shows
// where a page sits, not how the user got there, so a page reached from the
// sidebar still shows its section as the parent. The current page is a yellow
// block with a black border (as the role badge on the profile page is), so it
// stands out from the links.
defineProps({
  items: {
    type: Array,
    required: true,
    validator: (items) => items.length > 0 && items.every((item) => typeof item.label === "string"),
  },
});
</script>

<template>
  <nav aria-label="Breadcrumb" class="mb-6 text-sm font-medium">
    <ol class="flex flex-wrap items-center gap-2">
      <template v-for="(item, index) in items" :key="index">
        <li v-if="index > 0" aria-hidden="true">/</li>
        <li v-if="index < items.length - 1">
          <RouterLink :to="item.to" class="underline underline-offset-4 hover:bg-muted">
            {{ item.label }}
          </RouterLink>
        </li>
        <li
          v-else
          aria-current="page"
          class="break-words border-2 border-ink bg-bauhaus-yellow px-2 py-0.5 font-bold"
        >
          {{ item.label }}
        </li>
      </template>
    </ol>
  </nav>
</template>
