<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausBreadcrumb from "@/components/common/BauhausBreadcrumb.vue";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausIcon from "@/components/common/BauhausIcon.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import BlockVenueModal from "@/components/venues/BlockVenueModal.vue";
import ChangeBlockModal from "@/components/venues/ChangeBlockModal.vue";
import DeactivateVenueModal from "@/components/venues/DeactivateVenueModal.vue";
import VenueGallery from "@/components/venues/VenueGallery.vue";
import { blockActions, blockSetBy } from "@/features/venues/blockChange";
import {
  ALL_BOOKING_STATUSES,
  blockReasonLabel,
  bookingStatusFilterOptions,
  UPCOMING_BOOKING_STATUSES,
  bookingStatusLabel,
  filterBookingRequests,
  formatEventReference,
  sortBookingRequests,
} from "@/features/venues/dashboard";
import { useVenueEditStore } from "@/features/venues/venueEditStore";
import {
  lastEditorName,
  stepIndex,
  summariseEditHistoryEntry,
  venueProfileTabs,
  venueSlides,
  formatVenuePeriod,
  inactiveReasonLabel,
} from "@/features/venues/venueProfile";
import { ACCESSIBILITY_FEATURES, FACILITIES, LAYOUTS, useVenuesStore } from "@/features/venues/venueSearchStore";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const venuesStore = useVenuesStore();
const venueEditStore = useVenueEditStore();
const authStore = useAuthStore();
const canEdit = computed(() => authStore.role === "venue_staff");

const labelFor = (list) => Object.fromEntries(list.map((entry) => [entry.value, entry.label]));
const layoutLabels = labelFor(LAYOUTS);
const facilityLabels = labelFor(FACILITIES);
const accessibilityLabels = labelFor(ACCESSIBILITY_FEATURES);

const venue = computed(() => venuesStore.selectedVenue);
const breadcrumbItems = computed(() => [
  { label: "Venues", to: { name: "venue-search" } },
  { label: venue.value?.name ?? "Venue" },
]);

const sgtFormatter = new Intl.DateTimeFormat("en-SG", {
  timeZone: "Asia/Singapore",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const formatPeriod = formatVenuePeriod;

const formatInstant = (value) => (value ? sgtFormatter.format(new Date(value)) : "Not recorded");

// SCRUM-67 AC2. `updated_at` comes from the SCRUM-39 trigger and is always
// present; `updated_by` is null until a venue is edited through a path that
// records the editor, so the two are worded separately rather than as one
// sentence that would read oddly with half of it missing.
const lastUpdated = computed(() => ({
  at: formatInstant(venue.value?.updated_at),
  by: lastEditorName(venue.value?.updated_by),
}));

// SCRUM-67 AC3. The Status choice and its filter are the booking requests page's own
// (features/venues/dashboard.js), so the two lists name and filter statuses the same way.
const upcomingBookings = computed(() => venue.value?.upcoming_bookings ?? []);
const upcomingBookingCount = computed(() => upcomingBookings.value.length);

// Photos first, then a schematic per supported layout (VC-R8).
const slides = computed(() => venueSlides(venue.value));

// The tabs carry counts, so a closed tab never implies there is nothing in it.
const tabs = computed(() => venueProfileTabs(venue.value));
const activeTab = ref("capacity");
// A different venue should open on its first tab rather than keeping whichever
// one the previous venue was left on.
watch(() => route.params.id, () => { activeTab.value = "capacity"; });

function moveTab(delta) {
  const keys = tabs.value.map((tab) => tab.key);
  const next = stepIndex(keys.indexOf(activeTab.value), keys.length, delta);
  activeTab.value = keys[next];
}

// History entries load on demand, the first time the tab opens, rather than
// on every page load — most visits never open it (SCRUM-63).
const historyEntries = computed(() => venueEditStore.history.map((entry) => ({ entry, diff: summariseEditHistoryEntry(entry) })));
watch(activeTab, (tab) => {
  if (tab === "history" && route.params.id) venueEditStore.loadHistory(route.params.id);
});

// Opens on every booking, tentative holds included (SCRUM-67 AC3): a venue with one hold
// must still show its confirmed bookings. Each venue starts from All statuses again.
const bookingStatus = ref(ALL_BOOKING_STATUSES);
watch(() => route.params.id, () => { bookingStatus.value = ALL_BOOKING_STATUSES; });
const statusOptions = computed(() =>
  bookingStatusFilterOptions(upcomingBookings.value, UPCOMING_BOOKING_STATUSES).map((option) => ({
    ...option,
    label: `${option.label} (${option.count})`,
  })),
);
const visibleBookings = computed(() =>
  sortBookingRequests(filterBookingRequests(upcomingBookings.value, { status: bookingStatus.value })),
);

async function load() {
  try {
    await venuesStore.fetchVenue(route.params.id);
  } catch {
    // The store keeps the message; the template shows it.
  }
}

// SCRUM-64: deactivate (with a preview of the bookings it would flag) and
// reactivate. Both endpoints return the updated venue, so the page shows it
// without a reload that would blank it while fetching.
const deactivateOpen = ref(false);
const reactivateOpen = ref(false);
// Page-local, not the shared store's `error`, which the edit page also sets.
const actionError = ref(null);
let refreshOnClose = false;

// Re-read the venue without blanking the page (`fetchVenue` clears it first):
// after a refusal the venue has usually changed under us, e.g. another tab
// already deactivated it.
async function refresh() {
  const id = venue.value.id;
  await venueEditStore.load(id);
  if (venueEditStore.venue && route.params.id === id) venuesStore.selectedVenue = venueEditStore.venue;
}

function openDeactivate() {
  venueEditStore.affected = [];
  actionError.value = null;
  deactivateOpen.value = true;
}

async function closeDeactivate() {
  deactivateOpen.value = false;
  venueEditStore.affected = [];
  actionError.value = null;
  if (refreshOnClose) {
    refreshOnClose = false;
    await refresh();
  }
}

async function afterSave() {
  venuesStore.selectedVenue = venueEditStore.venue;
  if (activeTab.value === "history") await venueEditStore.loadHistory(venue.value.id);
}

async function deactivate({ reason, note, confirm }) {
  actionError.value = null;
  try {
    const saved = await venueEditStore.deactivate(venue.value.id, { reason, note, version: venue.value.version }, { confirm });
    if (!saved) return;
    deactivateOpen.value = false;
    await afterSave();
  } catch (error) {
    actionError.value = error.message;
    refreshOnClose = true;
  }
}

// SCRUM-51: block the venue for a period, with the same preview-then-confirm
// as deactivation (CAL-R1). Once saved the modal lists the affected bookings
// (AC6); closing it re-reads the venue so the Blocks tab shows the new block.
const blockOpen = ref(false);

function openBlock() {
  venueEditStore.affected = [];
  venueEditStore.blockResult = null;
  actionError.value = null;
  blockOpen.value = true;
}

async function closeBlock() {
  const saved = Boolean(venueEditStore.blockResult);
  blockOpen.value = false;
  venueEditStore.affected = [];
  venueEditStore.blockResult = null;
  actionError.value = null;
  if (saved) {
    await refresh();
    if (activeTab.value === "history") await venueEditStore.loadHistory(venue.value.id);
  }
}

async function block(payload) {
  actionError.value = null;
  try {
    await venueEditStore.createBlock(venue.value.id, payload);
  } catch (error) {
    actionError.value = error.message;
  }
}

// SCRUM-54: end, shorten or remove a block. Once saved the modal lists the
// bookings the block no longer covers (AC5). Closing re-reads the venue after
// a save, or after a refusal, which usually means the block changed elsewhere.
const changingBlock = ref(null);
let blockChanged = false;

function openChangeBlock(target) {
  venueEditStore.clearBlockChange();
  actionError.value = null;
  blockChanged = false;
  changingBlock.value = target;
}

async function closeChangeBlock() {
  const reload = blockChanged || Boolean(venueEditStore.blockChangeResult);
  changingBlock.value = null;
  venueEditStore.clearBlockChange();
  actionError.value = null;
  if (reload) {
    await refresh();
    if (activeTab.value === "history") await venueEditStore.loadHistory(venue.value.id);
  }
}

async function changeBlock(payload) {
  actionError.value = null;
  try {
    await venueEditStore.changeBlock(venue.value.id, changingBlock.value.id, payload);
  } catch (error) {
    actionError.value = error.message;
    blockChanged = true;
  }
}

async function reactivate() {
  reactivateOpen.value = false;
  actionError.value = null;
  try {
    await venueEditStore.reactivate(venue.value.id, venue.value.version);
    await afterSave();
  } catch (error) {
    actionError.value = error.message;
    await refresh();
  }
}

onMounted(load);
watch(() => route.params.id, () => {
  actionError.value = null;
  load();
});
</script>

<template>
  <main class="py-8">
    <BauhausBreadcrumb :items="breadcrumbItems" />

    <p
      v-if="venuesStore.error && !venue"
      role="alert"
      class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-base font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ venuesStore.error }}
    </p>
    <p v-else-if="venuesStore.isLoading && !venue" class="text-base font-medium">Loading venue…</p>

    <template v-if="venue">
      <!-- The venue's details first, then the carousel (beside it on wide screens), both at least 24rem tall and the same height (the carousel stretches to match the details) -->
      <div class="lg:mb-8 lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-stretch lg:gap-8">
        <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow" compact class="mb-8 lg:mb-0 lg:min-h-96">
          <p class="text-sm font-bold opacity-90">
            {{ venue.is_active ? "Venue" : "Inactive venue" }}
          </p>
          <h1 class="mt-2 text-4xl font-bold leading-tight sm:text-5xl">{{ venue.name }}</h1>
          <p class="mt-3 text-base font-medium"><span class="font-bold">Location:</span> {{ venue.location }}</p>
          <p v-if="venue.description" class="mt-3 max-w-xl text-base font-medium"><span class="font-bold">Description:</span> {{ venue.description }}</p>
          <p class="mt-4 text-sm font-bold text-ink/70">
            Last updated {{ lastUpdated.at }} · by {{ lastUpdated.by }}
          </p>
          <div
            v-if="!venue.is_active"
            data-testid="venue-inactive-banner"
            class="mt-4 border-2 border-ink bg-canvas px-4 py-3 text-ink shadow-hard sm:border-4"
          >
            <p class="text-sm font-bold">Inactive: {{ inactiveReasonLabel(venue.inactive_reason) }}</p>
            <p v-if="venue.inactive_note" class="mt-1 text-base font-medium">{{ venue.inactive_note }}</p>
          </div>
          <div v-if="canEdit" class="mt-5 border-t-2 border-ink pt-4">
            <div class="grid w-fit grid-cols-2 gap-3">
              <BauhausButton :to="{ name: 'venue-edit', params: { id: venue.id } }" size="sm" full-width title="Change this venue's details">
                <BauhausIcon name="edit" />
                Edit venue
              </BauhausButton>
              <BauhausButton
                :to="{ name: 'venue-calendar', params: { venueId: venue.id } }"
                size="sm"
                variant="outline"
                full-width
                title="See when this venue is booked, held or blocked"
              >
                <BauhausIcon name="calendar" />
                View calendar
              </BauhausButton>
              <p class="col-span-2 mt-1 text-sm font-bold text-ink/70">Availability</p>
              <BauhausButton size="sm" variant="outline" full-width title="Take this venue out of use for a period" @click="openBlock">
                <BauhausIcon name="block" />
                Block venue
              </BauhausButton>
              <BauhausButton
                v-if="venue.is_active"
                size="sm"
                variant="outline"
                full-width
                title="Remove this venue from the catalogue"
                @click="openDeactivate"
              >
                <BauhausIcon name="deactivate" />
                Deactivate venue
              </BauhausButton>
              <BauhausButton
                v-else
                size="sm"
                variant="outline"
                full-width
                title="Put this venue back in the catalogue"
                @click="reactivateOpen = true"
              >
                <BauhausIcon name="reactivate" />
                Reactivate venue
              </BauhausButton>
            </div>
          </div>
          <p
            v-if="actionError && !deactivateOpen && !blockOpen && !changingBlock"
            role="alert"
            class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-base font-bold text-canvas"
          >
            {{ actionError }}
          </p>
        </BauhausCard>

        <VenueGallery :slides="slides" :venue-name="venue.name" class="lg:mb-0" data-testid="venue-gallery" />
      </div>

      <DeactivateVenueModal
        :open="deactivateOpen"
        :venue-name="venue.name"
        :affected="venueEditStore.affected"
        :busy="venueEditStore.isSaving"
        :error="actionError"
        @confirm="deactivate"
        @cancel="closeDeactivate"
      />
      <BlockVenueModal
        :open="blockOpen"
        :venue-name="venue.name"
        :affected="venueEditStore.affected"
        :result="venueEditStore.blockResult"
        :busy="venueEditStore.isSaving"
        :error="actionError"
        @confirm="block"
        @cancel="closeBlock"
      />
      <ChangeBlockModal
        :open="Boolean(changingBlock)"
        :venue-name="venue.name"
        :block="changingBlock"
        :result="venueEditStore.blockChangeResult"
        :busy="venueEditStore.isSaving"
        :error="actionError"
        @confirm="changeBlock"
        @cancel="closeChangeBlock"
      />
      <ConfirmModal
        :open="reactivateOpen"
        :title="`Reactivate ${venue.name}?`"
        message="It will appear in venue search again. Bookings flagged Affected stay flagged."
        confirm-label="Reactivate"
        cancel-label="Cancel"
        @confirm="reactivate"
        @stay="reactivateOpen = false"
      />

      <div
        class="mb-6 flex flex-wrap gap-2"
        role="tablist"
        aria-label="Venue profile sections"
        @keydown.left.prevent="moveTab(-1)"
        @keydown.right.prevent="moveTab(1)"
      >
        <button
          v-for="tab in tabs"
          :id="`tab-${tab.key}`"
          :key="tab.key"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.key ? 'true' : 'false'"
          :aria-controls="`panel-${tab.key}`"
          :tabindex="activeTab === tab.key ? 0 : -1"
          class="border-2 border-ink px-4 py-2 text-sm font-bold active-press"
          :class="activeTab === tab.key ? 'bg-ink text-canvas shadow-hard' : 'bg-canvas text-ink hover:bg-muted'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}<span v-if="tab.count !== null"> · {{ tab.count }}</span>
        </button>
      </div>

      <BauhausCard
        v-if="activeTab === 'capacity'"
        id="panel-capacity"
        role="tabpanel"
        aria-labelledby="tab-capacity"
        background="white"
        accent="none"
      >
        <h2 class="mb-5 text-xl font-bold">Capacity &amp; hours</h2>
        <dl class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-sm font-bold text-ink/70">Capacity</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ venue.capacity }} <span class="text-base">pax</span></dd>
          </div>
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-sm font-bold text-ink/70">Open</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ venue.opens_at.slice(0, 5) }}–{{ venue.closes_at.slice(0, 5) }}</dd>
          </div>
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-sm font-bold text-ink/70">Default setup</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ venue.setup_minutes }} <span class="text-base">minutes</span></dd>
          </div>
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-sm font-bold text-ink/70">Default turnaround</dt>
            <dd class="mt-1 text-2xl font-bold leading-tight">{{ venue.turnaround_minutes }} <span class="text-base">minutes</span></dd>
          </div>
        </dl>
        <p class="mt-4 text-base font-medium text-ink/70">Defaults apply to new booking requests only. Existing bookings keep their own times.</p>
        <h3 class="mb-2 mt-6 text-base font-bold">Layouts</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="entry in venue.layouts"
            :key="entry.layout"
            class="border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-sm font-bold"
          >
            {{ layoutLabels[entry.layout] ?? entry.layout }}
            <span v-if="entry.capacity_for_layout">· {{ entry.capacity_for_layout }} pax</span>
          </li>
          <li v-if="!venue.layouts.length" class="text-base font-medium">None recorded</li>
        </ul>
      </BauhausCard>

      <BauhausCard
        v-else-if="activeTab === 'facilities'"
        id="panel-facilities"
        role="tabpanel"
        aria-labelledby="tab-facilities"
        background="white"
        accent="none"
      >
        <h2 class="mb-5 text-xl font-bold">Facilities &amp; access</h2>
        <h3 class="mb-2 text-base font-bold">Facilities</h3>
        <ul class="mb-6 flex flex-wrap gap-2">
          <li v-for="f in venue.facilities" :key="f" class="border-2 border-ink px-3 py-1 text-sm font-bold">
            {{ facilityLabels[f] ?? f }}
          </li>
          <li v-if="!venue.facilities.length" class="text-base font-medium">None recorded</li>
        </ul>
        <h3 class="mb-2 text-base font-bold">Accessibility</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="a in venue.accessibility_features"
            :key="a"
            class="border-2 border-ink px-3 py-1 text-sm font-bold"
          >
            {{ accessibilityLabels[a] ?? a }}
          </li>
          <li v-if="!venue.accessibility_features.length" class="text-base font-medium">None recorded</li>
        </ul>
        <dl class="mt-6 grid gap-4 md:grid-cols-2">
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-base font-bold">Emergency access</dt>
            <dd class="mt-2 whitespace-pre-wrap break-words text-base font-medium">{{ venue.emergency_access ?? 'Not recorded' }}</dd>
          </div>
          <div class="border-2 border-ink px-4 py-3">
            <dt class="text-base font-bold">Restrictions</dt>
            <dd class="mt-2 whitespace-pre-wrap break-words text-base font-medium">{{ venue.restrictions ?? 'Not recorded' }}</dd>
          </div>
        </dl>
      </BauhausCard>

      <BauhausCard
        v-else-if="activeTab === 'bookings'"
        id="panel-bookings"
        role="tabpanel"
        aria-labelledby="tab-bookings"
        background="white"
        accent="none"
        data-testid="upcoming-bookings"
      >
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-xl font-bold">Upcoming bookings</h2>
          <p class="border-2 border-ink px-3 py-1 text-base font-bold">
            {{ upcomingBookingCount }} upcoming {{ upcomingBookingCount === 1 ? "booking" : "bookings" }}
          </p>
        </div>
        <p class="mb-5 text-base font-medium text-ink/70">
          Singapore time. Every booking here occupies the venue, tentative ones included.
        </p>

        <BauhausEmptyState
          v-if="upcomingBookingCount === 0"
          title="No upcoming bookings"
          detail="Nothing is confirmed or held on this venue from now on."
        />

        <template v-else>
          <div class="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <BauhausSelect
              v-model="bookingStatus"
              label="Status"
              aria-label="Booking status"
              :options="statusOptions"
              :show-placeholder="false"
              compact
            />
          </div>

          <div id="panel-group-bookings">
            <ul v-if="visibleBookings.length" class="flex flex-col gap-3">
              <li v-for="booking in visibleBookings" :key="booking.id">
                <!-- Venue staff open the booking itself. Other roles see the row only: the booking page
                     is limited to staff and the event's assigned coordinator, which the venue page can't tell. -->
                <component
                  :is="canEdit ? RouterLink : 'div'"
                  v-bind="canEdit ? { to: { name: 'booking-request', params: { id: booking.id } } } : {}"
                  :class="canEdit ? 'hover:bg-muted active-press' : ''"
                  class="flex flex-wrap items-center justify-between gap-3 border-2 border-ink px-4 py-3"
                >
                  <span class="min-w-0">
                    <span class="block text-lg font-bold leading-tight">{{ formatEventReference(booking) }}</span>
                    <span class="mt-1 flex items-center gap-2 text-base font-medium">
                      <BauhausIcon name="calendar" class="text-ink/70" />
                      {{ formatPeriod(booking.period) }}
                    </span>
                  </span>
                  <span class="flex shrink-0 items-center gap-3">
                    <span class="border-2 border-ink px-3 py-1 text-base font-bold">{{ bookingStatusLabel(booking.status) }}</span>
                    <span v-if="canEdit" class="text-base font-bold underline decoration-2 underline-offset-4">View booking →</span>
                  </span>
                </component>
              </li>
            </ul>
            <p v-else class="text-base font-medium text-ink/70">None.</p>
          </div>
        </template>
      </BauhausCard>

      <BauhausCard
        v-else-if="activeTab === 'blocks'"
        id="panel-blocks"
        role="tabpanel"
        aria-labelledby="tab-blocks"
        background="white"
        accent="none"
        data-testid="upcoming-blocks"
      >
        <h2 class="mb-3 text-xl font-bold">Blocks</h2>
        <p class="mb-5 text-base font-medium text-ink/70">
          Singapore time. Periods venue staff have made unbookable, from now on.
        </p>
        <ul class="flex flex-col gap-3">
          <li
            v-for="block in venue.upcoming_blocks"
            :key="block.id"
            class="flex flex-wrap items-center justify-between gap-3 border-2 border-ink px-4 py-3"
          >
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-3">
                <span class="border-2 border-ink bg-bauhaus-red px-3 py-1 text-base font-bold text-canvas">
                  {{ blockReasonLabel(block.reason) }}
                </span>
                <span class="text-lg font-bold leading-tight">{{ formatPeriod(block.period) }}</span>
              </div>
              <p v-if="block.notes" class="mt-2 text-base font-medium">{{ block.notes }}</p>
              <!-- SCRUM-54 AC1, AC9: venue staff see who set it and when, and change it. -->
              <p v-if="canEdit" class="mt-1 text-base font-medium text-ink/70">{{ blockSetBy(block) }}</p>
            </div>
            <BauhausButton
              v-if="canEdit && blockActions(block).length"
              type="button"
              variant="outline"
              size="sm"
              :aria-label="`Change block ${formatPeriod(block.period)}`"
              @click="openChangeBlock(block)"
            >
              Change
            </BauhausButton>
          </li>
          <li v-if="!venue.upcoming_blocks.length" class="border-2 border-ink px-4 py-3 text-base font-medium">No blocks scheduled.</li>
        </ul>
      </BauhausCard>

      <BauhausCard
        v-else
        id="panel-history"
        role="tabpanel"
        aria-labelledby="tab-history"
        background="white"
        accent="none"
        data-testid="edit-history"
      >
        <h2 class="mb-3 text-xl font-bold">History</h2>
        <p class="mb-5 text-base font-medium text-ink/70">Every saved edit to this venue's details, newest first.</p>

        <BauhausEmptyState
          v-if="!venueEditStore.isLoading && historyEntries.length === 0"
          title="No edits recorded"
          detail="This venue's details have not been changed since it was added."
        />
        <ul v-else class="flex flex-col gap-3">
          <li v-for="{ entry, diff } in historyEntries" :key="entry.id" class="border-2 border-ink">
            <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b-2 border-ink px-4 py-2">
              <p class="text-base font-bold">{{ entry.actor?.full_name ?? "Unknown user" }}</p>
              <p class="text-base font-medium text-ink/70">{{ formatInstant(entry.at) }}</p>
            </div>
            <ul class="flex flex-col gap-2 px-4 py-3">
              <li v-for="change in diff" :key="change.field" class="grid gap-1 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-4">
                <span class="text-base font-bold">{{ change.label }}</span>
                <span class="text-base font-medium">
                  <span class="text-ink/70">{{ change.before }}</span> → {{ change.after }}
                </span>
              </li>
            </ul>
          </li>
        </ul>
      </BauhausCard>
    </template>
  </main>
</template>
