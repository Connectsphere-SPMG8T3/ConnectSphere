<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import { formatNotificationTime } from "@/features/notifications/format";
import { useNotificationsStore } from "@/features/notifications/notificationsStore";

// The bell every signed-in role has (113). It owns the polling: it starts when the
// bar mounts and stops, with the store cleared, when the bar goes (logout).
const store = useNotificationsStore();
const route = useRoute();
const container = ref(null);

// A document listener rather than a click-away layer: a layer inside the header's
// stacking context can't cover the sidebar, which sits above it on desktop.
function closeOnOutsideClick(event) {
  if (store.isOpen && container.value && !container.value.contains(event.target)) store.close();
}

onMounted(() => {
  store.start();
  document.addEventListener("click", closeOnOutsideClick);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", closeOnOutsideClick);
  store.stop();
});

// A page change closes the panel, as the old placeholder panel did.
watch(
  () => route.fullPath,
  () => store.close(),
);

const badge = computed(() => (store.count > 99 ? "99+" : String(store.count)));
const bellLabel = computed(() =>
  store.count > 0 ? `Notifications, ${store.count} unread` : "Notifications",
);

function toggle() {
  if (store.isOpen) store.close();
  else store.open();
}

// Opening an item marks it read and closes the panel; a link then navigates.
function select(item) {
  store.markRead(item.id);
  store.close();
}
</script>

<template>
  <div ref="container" class="relative">
    <button
      type="button"
      class="relative flex h-10 w-10 items-center justify-center border-2 border-ink shadow-hard active-press"
      :class="store.isOpen ? 'bg-bauhaus-yellow' : 'bg-canvas hover:bg-muted'"
      :aria-label="bellLabel"
      :aria-expanded="store.isOpen"
      @click="toggle"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="h-5 w-5"
        aria-hidden="true"
      >
        <path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8" />
        <path d="M13.7 21a2 2 0 0 1-3.4 0" />
      </svg>
      <span
        v-if="store.count > 0"
        data-testid="notification-badge"
        class="absolute -right-2 -top-2 flex h-5 min-w-[1.25rem] items-center justify-center border-2 border-ink bg-bauhaus-red px-1 text-xs font-bold leading-none text-canvas"
        aria-hidden="true"
      >
        {{ badge }}
      </span>
    </button>

    <div
      v-if="store.isOpen"
      class="absolute right-0 top-full z-20 mt-3 w-72 max-w-[calc(100vw-2rem)] border-2 border-ink bg-surface shadow-hard sm:w-96 sm:border-4"
    >
      <div class="flex items-center justify-between gap-2 border-b-2 border-ink px-4 py-3">
        <p class="text-xs font-bold">Notifications</p>
        <button
          v-if="store.count > 0"
          type="button"
          class="border-2 border-ink bg-canvas px-2 py-1 text-xs font-bold hover:bg-muted active-press"
          @click="store.markAllRead()"
        >
          Mark all as read
        </button>
      </div>

      <p v-if="store.error" role="alert" class="px-4 py-3 text-sm font-bold text-bauhaus-red">
        {{ store.error }}
      </p>

      <p
        v-if="store.isLoading && store.items.length === 0"
        class="px-4 py-3 text-xs font-bold text-ink/70"
      >
        Loading
      </p>
      <p
        v-else-if="!store.isLoading && !store.error && store.items.length === 0"
        class="px-4 py-3 text-xs font-bold text-ink/70"
      >
        No notifications
      </p>

      <ul v-if="store.items.length > 0" class="max-h-96 overflow-y-auto">
        <li
          v-for="item in store.items"
          :key="item.id"
          :aria-label="item.read ? null : `${item.message} (unread)`"
          class="border-b-2 border-ink/20 last:border-b-0"
        >
          <component
            :is="item.link ? RouterLink : 'button'"
            v-bind="item.link ? { to: item.link } : { type: 'button' }"
            class="flex w-full items-start gap-3 px-4 py-3 text-left"
            :class="item.read ? 'hover:bg-muted' : 'bg-bauhaus-yellow/20 hover:bg-muted'"
            @click="select(item)"
          >
            <!-- Unread: a solid square marker on a tinted row; read: an empty slot, so text stays aligned. -->
            <span
              v-if="!item.read"
              data-testid="unread-marker"
              class="mt-1.5 h-2.5 w-2.5 shrink-0 border-2 border-ink bg-bauhaus-yellow"
              aria-hidden="true"
            ></span>
            <span v-else class="mt-1.5 h-2.5 w-2.5 shrink-0" aria-hidden="true"></span>
            <span class="min-w-0">
              <span class="block text-sm text-ink" :class="item.read ? 'font-medium text-ink/70' : 'font-bold'">
                {{ item.message }}
              </span>
              <span class="mt-1 block text-xs font-bold text-ink/60">
                {{ formatNotificationTime(item.created_at) }}
              </span>
            </span>
          </component>
        </li>
      </ul>

      <button
        v-if="store.nextBefore"
        type="button"
        class="block w-full border-t-2 border-ink px-4 py-3 text-xs font-bold hover:bg-muted active-press"
        @click="store.loadMore()"
      >
        Older notifications
      </button>
    </div>
  </div>
</template>
