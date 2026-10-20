import { defineStore } from "pinia";

import { createPoller } from "@/features/notifications/polling";
import { notificationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const PAGE_SIZE = 20;

// The poller and the role watch are not state: they live beside the store, one
// set per store instance, so a test's fresh Pinia never inherits the last one's.
const running = new WeakMap();

// Counts how many times the list was restarted from the top (or cleared), per store.
const generations = new WeakMap();
const bumpGeneration = (store) => {
  const next = (generations.get(store) ?? 0) + 1;
  generations.set(store, next);
  return next;
};

const initialState = () => ({
  count: 0,
  latestAt: null,
  items: [],
  nextBefore: null,
  isOpen: false,
  isLoading: false,
  error: null,
});

/**
 * The notification bell (113, ADR-0004): the unread count is polled every 10 seconds
 * while the tab is visible, and the list is fetched when the panel opens or, while it
 * is open, when the poll sees something new.
 *
 * Everything is the caller's, in the role they are acting as. Each request re-checks
 * that role after its await, so a slow response for the role a user just left can
 * never land on the one they switched to (the same guard as useEventCommentsStore).
 */
export const useNotificationsStore = defineStore("notifications", {
  state: initialState,

  actions: {
    async poll() {
      const auth = useAuthStore();
      if (!auth.token) return;
      const role = auth.role;
      let response;
      try {
        response = await auth.withSession((token) => notificationsApi.unreadCount(token));
      } catch {
        // An outage skips this tick and keeps the last good count; a rejected
        // session has already been ended by the auth store.
        return;
      }
      if (auth.role !== role) return;
      const changed = response.count !== this.count || response.latest_at !== this.latestAt;
      this.count = response.count;
      this.latestAt = response.latest_at;
      if (this.isOpen && changed) await this.loadList();
    },

    async open() {
      this.isOpen = true;
      await this.loadList();
    },

    close() {
      this.isOpen = false;
    },

    async loadList() {
      await this.fetchPage(null);
    },

    async loadMore() {
      if (!this.nextBefore) return;
      await this.fetchPage(this.nextBefore);
    },

    async fetchPage(before) {
      const auth = useAuthStore();
      const role = auth.role;
      // A reload from the top starts a new generation; an older page asked for under
      // an earlier one belongs to a list that has since been replaced, so it is dropped.
      const generation = before ? generations.get(this) : bumpGeneration(this);
      const current = () => auth.role === role && generations.get(this) === generation;
      this.isLoading = true;
      this.error = null;
      try {
        const params = before ? { limit: PAGE_SIZE, before } : { limit: PAGE_SIZE };
        const page = await auth.withSession((token) => notificationsApi.list(params, token));
        if (!current()) return;
        this.items = before ? [...this.items, ...page.items] : page.items;
        this.nextBefore = page.next_before;
      } catch (error) {
        if (current()) this.error = error.message;
      } finally {
        if (current()) this.isLoading = false;
      }
    },

    async markRead(notificationId) {
      const auth = useAuthStore();
      const role = auth.role;
      try {
        await auth.withSession((token) => notificationsApi.markRead(notificationId, token));
      } catch (error) {
        if (auth.role === role) this.error = error.message;
        return;
      }
      if (auth.role !== role) return;
      const item = this.items.find((entry) => entry.id === notificationId);
      if (item && !item.read) {
        item.read = true;
        this.count = Math.max(0, this.count - 1);
      }
    },

    async markAllRead() {
      const auth = useAuthStore();
      const role = auth.role;
      try {
        await auth.withSession((token) => notificationsApi.markAllRead(token));
      } catch (error) {
        if (auth.role === role) this.error = error.message;
        return;
      }
      if (auth.role !== role) return;
      this.items.forEach((item) => {
        item.read = true;
      });
      this.count = 0;
    },

    reset() {
      bumpGeneration(this);
      Object.assign(this, initialState());
    },

    /** Begin polling, and start over whenever the session switches role. */
    start() {
      if (running.has(this)) return;
      const auth = useAuthStore();
      let lastRole = auth.role;
      const poller = createPoller({ tick: () => this.poll() });
      const unsubscribe = auth.$subscribe(
        () => {
          if (auth.role === lastRole) return;
          lastRole = auth.role;
          this.reset();
          this.poll();
        },
        { flush: "sync" },
      );
      running.set(this, { poller, unsubscribe });
      poller.start();
    },

    stop() {
      const handles = running.get(this);
      if (handles) {
        handles.poller.stop();
        handles.unsubscribe();
        running.delete(this);
      }
      this.reset();
    },
  },
});
