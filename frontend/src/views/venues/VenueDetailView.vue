<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import BlockVenueModal from "@/components/venues/BlockVenueModal.vue";
import DeactivateVenueModal from "@/components/venues/DeactivateVenueModal.vue";
import VenueGallery from "@/components/venues/VenueGallery.vue";
import { blockReasonLabel, formatEventReference } from "@/features/venues/dashboard";
import { useVenueEditStore } from "@/features/venues/venueEditStore";
import {
  defaultBookingGroupKey,
  groupUpcomingBookings,
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

// SCRUM-67 AC3. Counting and grouping live in features/venues/venueProfile.js,
// so the rules are testable without mounting this view.
const bookingGroups = computed(() => groupUpcomingBookings(venue.value?.upcoming_bookings));
const upcomingBookingCount = computed(() => venue.value?.upcoming_bookings?.length ?? 0);

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

// The booking statuses are tabbed too, one level in. The selection follows the
// data rather than defaulting to "Confirmed": a venue whose only commitment is
// a hold would otherwise open on an empty panel reading as "nothing booked".
const activeGroup = ref(defaultBookingGroupKey(bookingGroups.value));
watch(bookingGroups, (groups) => {
  activeGroup.value = defaultBookingGroupKey(groups);
});
const currentGroup = computed(
  () => bookingGroups.value.find((group) => group.key === activeGroup.value) ?? bookingGroups.value[0],
);

function moveGroup(delta) {
  const keys = bookingGroups.value.map((group) => group.key);
  const next = stepIndex(keys.indexOf(activeGroup.value), keys.length, delta);
  activeGroup.value = keys[next];
}

// Tone → pill class maps are spelled out because Tailwind's scanner cannot see
// a class built by interpolation. VenueStaffDashboard keeps its own copy; see
// docs/IMPLEMENTATION_MAP.md §5 for the note on extracting it.
const pillClasses = {
  blue: "border-2 border-ink bg-bauhaus-blue text-canvas",
  yellow: "border-2 border-ink bg-bauhaus-yellow text-ink",
  red: "border-2 border-ink bg-bauhaus-red text-canvas",
  plain: "border-2 border-ink bg-canvas text-ink",
};

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
  <main class="py-12">
    <RouterLink
      :to="{ name: 'venue-search' }"
      class="mb-8 inline-block text-xs font-bold underline decoration-2 underline-offset-4"
    >
      ← Back to venue search
    </RouterLink>

    <p
      v-if="venuesStore.error && !venue"
      role="alert"
      class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
    >
      {{ venuesStore.error }}
    </p>
    <p v-else-if="venuesStore.isLoading && !venue" class="text-sm font-medium">Loading venue…</p>

    <template v-if="venue">
      <VenueGallery :slides="slides" :venue-name="venue.name" data-testid="venue-gallery" />

      <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow" class="mb-8">
        <p class="text-xs font-bold opacity-80">
          {{ venue.is_active ? "Venue" : "Inactive venue" }}
        </p>
        <h1 class="mt-2 text-4xl font-bold leading-tight sm:text-5xl">{{ venue.name }}</h1>
        <p class="mt-3 text-sm font-medium">{{ venue.location }}</p>
        <p v-if="venue.description" class="mt-3 max-w-xl text-sm font-medium opacity-90">{{ venue.description }}</p>
        <p class="mt-4 text-xs font-bold text-ink/70">
          Last updated {{ lastUpdated.at }} · by {{ lastUpdated.by }}
        </p>
        <div
          v-if="!venue.is_active"
          data-testid="venue-inactive-banner"
          class="mt-4 border-2 border-ink bg-canvas px-4 py-3 text-ink shadow-hard sm:border-4"
        >
          <p class="text-xs font-bold">Inactive: {{ inactiveReasonLabel(venue.inactive_reason) }}</p>
          <p v-if="venue.inactive_note" class="mt-1 text-sm font-medium">{{ venue.inactive_note }}</p>
        </div>
        <div v-if="canEdit" class="mt-4 flex flex-wrap gap-3">
          <RouterLink
            :to="{ name: 'venue-edit', params: { id: venue.id } }"
            class="inline-block border-2 border-ink bg-canvas px-4 py-2 text-xs font-bold text-ink shadow-hard active-press sm:border-4"
          >
            Edit venue
          </RouterLink>
          <button
            v-if="venue.is_active"
            type="button"
            class="border-2 border-ink bg-canvas px-4 py-2 text-xs font-bold text-ink shadow-hard active-press sm:border-4"
            @click="openDeactivate"
          >
            Deactivate venue
          </button>
          <button
            v-else
            type="button"
            class="border-2 border-ink bg-canvas px-4 py-2 text-xs font-bold text-ink shadow-hard active-press sm:border-4"
            @click="reactivateOpen = true"
          >
            Reactivate venue
          </button>
          <button
            type="button"
            class="border-2 border-ink bg-canvas px-4 py-2 text-xs font-bold text-ink shadow-hard active-press sm:border-4"
            @click="openBlock"
          >
            Block venue
          </button>
        </div>
        <p
          v-if="actionError && !deactivateOpen && !blockOpen"
          role="alert"
          class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
        >
          {{ actionError }}
        </p>
      </BauhausCard>

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
          class="border-2 border-ink px-4 py-2 text-xs font-bold active-press"
          :class="activeTab === tab.key ? 'bg-ink text-canvas shadow-hard' : 'bg-canvas text-ink'"
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
        <h2 class="mb-4 text-lg font-bold">Capacity &amp; hours</h2>
        <dl class="grid grid-cols-2 gap-y-2 text-sm">
          <dt class="text-xs font-bold text-ink/70">Capacity</dt>
          <dd class="font-medium">{{ venue.capacity }} pax</dd>
          <dt class="text-xs font-bold text-ink/70">Open</dt>
          <dd class="font-medium">{{ venue.opens_at.slice(0, 5) }}–{{ venue.closes_at.slice(0, 5) }}</dd>
          <dt class="text-xs font-bold text-ink/70">Default setup</dt>
          <dd class="font-medium">{{ venue.setup_minutes }} minutes</dd>
          <dt class="text-xs font-bold text-ink/70">Default turnaround</dt>
          <dd class="font-medium">{{ venue.turnaround_minutes }} minutes</dd>
        </dl>
        <p class="mt-4 text-sm font-medium">Defaults apply to new booking requests only. Existing bookings keep their own times.</p>
        <h3 class="mb-2 mt-6 text-xs font-bold text-ink/70">Layouts</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="entry in venue.layouts"
            :key="entry.layout"
            class="border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-xs font-bold"
          >
            {{ layoutLabels[entry.layout] ?? entry.layout }}
            <span v-if="entry.capacity_for_layout">· {{ entry.capacity_for_layout }} pax</span>
          </li>
          <li v-if="!venue.layouts.length" class="text-sm font-medium">None recorded</li>
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
        <h2 class="mb-4 text-lg font-bold">Facilities &amp; access</h2>
        <h3 class="mb-2 text-xs font-bold text-ink/70">Facilities</h3>
        <ul class="mb-6 flex flex-wrap gap-2">
          <li v-for="f in venue.facilities" :key="f" class="border-2 border-ink px-3 py-1 text-xs font-bold">
            {{ facilityLabels[f] ?? f }}
          </li>
          <li v-if="!venue.facilities.length" class="text-sm font-medium">None recorded</li>
        </ul>
        <h3 class="mb-2 text-xs font-bold text-ink/70">Accessibility</h3>
        <ul class="flex flex-wrap gap-2">
          <li
            v-for="a in venue.accessibility_features"
            :key="a"
            class="border-2 border-ink px-3 py-1 text-xs font-bold"
          >
            {{ accessibilityLabels[a] ?? a }}
          </li>
          <li v-if="!venue.accessibility_features.length" class="text-sm font-medium">None recorded</li>
        </ul>
        <dl class="mt-6 space-y-4 text-sm">
          <div><dt class="text-xs font-bold text-ink/70">Emergency access</dt><dd class="mt-2 whitespace-pre-wrap break-words font-medium">{{ venue.emergency_access ?? 'Not recorded' }}</dd></div>
          <div><dt class="text-xs font-bold text-ink/70">Restrictions</dt><dd class="mt-2 whitespace-pre-wrap break-words font-medium">{{ venue.restrictions ?? 'Not recorded' }}</dd></div>
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
        <div class="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 class="text-lg font-bold">Upcoming bookings</h2>
          <p class="text-xs font-bold text-ink/70">
            {{ upcomingBookingCount }} upcoming {{ upcomingBookingCount === 1 ? "booking" : "bookings" }}
          </p>
        </div>
        <p class="mb-4 text-xs font-medium text-ink/70">
          Singapore time. Every booking here occupies the venue, tentative ones included.
        </p>

        <BauhausEmptyState
          v-if="upcomingBookingCount === 0"
          title="No upcoming bookings"
          detail="Nothing is confirmed or held on this venue from now on."
        />

        <template v-else>
          <div
            class="mb-4 flex flex-wrap gap-2"
            role="tablist"
            aria-label="Booking status"
            @keydown.left.prevent="moveGroup(-1)"
            @keydown.right.prevent="moveGroup(1)"
          >
            <button
              v-for="group in bookingGroups"
              :id="`tab-group-${group.key}`"
              :key="group.key"
              type="button"
              role="tab"
              :aria-selected="activeGroup === group.key ? 'true' : 'false'"
              :aria-controls="`panel-group-${group.key}`"
              :tabindex="activeGroup === group.key ? 0 : -1"
              class="px-3 py-1.5 text-xs font-bold active-press"
              :class="[pillClasses[group.tone], activeGroup === group.key ? 'shadow-hard' : 'opacity-60']"
              @click="activeGroup = group.key"
            >
              {{ group.label }} · {{ group.bookings.length }}
            </button>
          </div>

          <div
            v-if="currentGroup"
            :id="`panel-group-${currentGroup.key}`"
            role="tabpanel"
            :aria-labelledby="`tab-group-${currentGroup.key}`"
          >
            <p class="mb-3 text-xs font-medium text-ink/70">{{ currentGroup.detail }}</p>
            <ul v-if="currentGroup.bookings.length" class="flex flex-col gap-2 text-sm">
              <li
                v-for="booking in currentGroup.bookings"
                :key="booking.id"
                class="flex flex-wrap items-center gap-x-3 gap-y-1 border-2 border-ink px-3 py-2"
              >
                <span class="font-bold">{{ formatEventReference(booking) }}</span>
                <span class="font-medium">{{ formatPeriod(booking.period) }}</span>
              </li>
            </ul>
            <p v-else class="text-sm font-medium text-ink/60">None.</p>
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
        <h2 class="mb-4 text-lg font-bold">Blocks</h2>
        <p class="mb-4 text-xs font-medium text-ink/70">
          Singapore time. Periods venue staff have made unbookable, from now on.
        </p>
        <ul class="flex flex-col gap-2 text-sm">
          <li v-for="block in venue.upcoming_blocks" :key="block.id" class="flex flex-wrap items-center gap-3">
            <span class="border-2 border-ink bg-bauhaus-red px-2 py-0.5 text-xs font-bold text-canvas">
              {{ blockReasonLabel(block.reason) }}
            </span>
            <span class="font-medium">{{ formatPeriod(block.period) }}</span>
            <span v-if="block.notes" class="text-ink/70">{{ block.notes }}</span>
          </li>
          <li v-if="!venue.upcoming_blocks.length" class="font-medium">No blocks scheduled.</li>
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
        <h2 class="mb-4 text-lg font-bold">History</h2>
        <p class="mb-4 text-xs font-medium text-ink/70">Every saved edit to this venue's details, newest first.</p>

        <BauhausEmptyState
          v-if="!venueEditStore.isLoading && historyEntries.length === 0"
          title="No edits recorded"
          detail="This venue's details have not been changed since it was added."
        />
        <ul v-else class="flex flex-col gap-3 text-sm">
          <li v-for="{ entry, diff } in historyEntries" :key="entry.id" class="border-2 border-ink px-3 py-2">
            <p class="font-bold">
              {{ formatInstant(entry.at) }} · {{ entry.actor?.full_name ?? "Unknown user" }}
            </p>
            <ul class="mt-2 flex flex-col gap-1">
              <li v-for="change in diff" :key="change.field" class="text-ink/80">
                <span class="font-bold">{{ change.label }}:</span> {{ change.before }} → {{ change.after }}
              </li>
            </ul>
          </li>
        </ul>
      </BauhausCard>
    </template>
  </main>
</template>
