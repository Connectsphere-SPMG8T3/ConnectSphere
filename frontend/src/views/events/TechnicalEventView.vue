<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import EquipmentLineArrangement from "@/components/equipment/EquipmentLineArrangement.vue";
import { STATUS_LABELS as EVENT_STATUS_LABELS } from "@/features/events/dashboard";
import {
  exitConfirmationText,
  formatTechnicalTime,
  hasLiveLines,
  historyActor,
  historyEntryText,
  isOpenForArrangements,
  TECHNICAL_STATUS_BADGE_CLASSES,
  TECHNICAL_STATUS_LABELS,
} from "@/features/equipment/technical";
import { useTechnicalEventStore } from "@/features/equipment/technicalEventStore";

// SCRUM-24: Technical Support arrange one event's equipment. Thin by design:
// the store talks to the API, EquipmentLineArrangement handles each line.
const route = useRoute();
const router = useRouter();
const store = useTechnicalEventStore();

const view = computed(() => (store.view?.event.id === route.params.id ? store.view : null));
const open = computed(() => !!view.value && isOpenForArrangements(view.value.event.status));
const showExit = computed(() => !!view.value && hasLiveLines(view.value.lines));

watch(() => route.params.id, (id) => { if (id) store.load(id); }, { immediate: true });
</script>

<template>
  <main class="break-words py-8">
    <BauhausButton variant="outline" class="mb-8" @click="router.push({ name: 'dashboard-tech-support' })">Back to dashboard</BauhausButton>
    <p v-if="store.error" role="alert" class="mb-6 border-4 border-ink p-4 font-bold">{{ store.error }}</p>
    <p v-if="store.isLoading && !view" class="font-bold" role="status">Loading equipment…</p>

    <template v-if="view">
      <BauhausCard background="yellow" accent="none" class="mb-8">
        <h1 class="text-4xl font-bold leading-tight sm:text-5xl">{{ view.event.name }}</h1>
        <dl class="mt-6 grid gap-4 sm:grid-cols-2">
          <div><dt class="font-bold">Event status</dt><dd>{{ EVENT_STATUS_LABELS[view.event.status] ?? view.event.status }}</dd></div>
          <div><dt class="font-bold">Coordinator</dt><dd>{{ view.event.coordinator_name ?? "Not assigned" }}</dd></div>
          <div><dt class="font-bold">Starts</dt><dd>{{ formatTechnicalTime(view.event.starts_at) }}</dd></div>
          <div><dt class="font-bold">Ends</dt><dd>{{ formatTechnicalTime(view.event.ends_at) }}</dd></div>
          <div>
            <dt class="font-bold">Technical status</dt>
            <dd class="mt-1">
              <span class="inline-block border-2 border-ink px-3 py-1 text-xs font-bold" :class="TECHNICAL_STATUS_BADGE_CLASSES[view.technical_status]">
                {{ TECHNICAL_STATUS_LABELS[view.technical_status] ?? view.technical_status }}
              </span>
            </dd>
          </div>
        </dl>
        <p v-if="!open" class="mt-6 font-bold">This event is {{ (EVENT_STATUS_LABELS[view.event.status] ?? view.event.status).toLowerCase() }}, so its equipment can no longer be changed.</p>
      </BauhausCard>

      <div class="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="lines-title" class="min-w-0">
          <h2 id="lines-title" class="mb-4 text-2xl font-bold">Equipment lines</h2>
          <BauhausEmptyState v-if="!view.lines.length" title="No equipment requested" detail="Technical status is Not required." />
          <div v-else class="flex flex-col gap-4">
            <EquipmentLineArrangement
              v-for="line in view.lines"
              :key="line.id"
              :line="line"
              :open="open"
              :busy="store.busy === line.id"
              :locked="!!store.busy && store.busy !== line.id"
              :error="store.lineErrors[line.id] ?? null"
              @reserve="store.reserve(line.id)"
              @not-available="(reason) => store.markNotAvailable(line.id, reason)"
              @save-note="(note) => store.saveNote(line.id, note)"
            />
          </div>
        </section>

        <div class="flex min-w-0 flex-col gap-8">
          <BauhausCard v-if="showExit" background="white" accent="none">
            <h2 class="text-2xl font-bold">Exit check</h2>
            <label class="mt-4 flex cursor-pointer items-start gap-3 border-2 border-ink p-3 font-bold" :class="view.exit_confirmation ? 'bg-bauhaus-yellow' : 'bg-canvas'">
              <input
                type="checkbox"
                class="mt-1 h-5 w-5 shrink-0 accent-bauhaus-red"
                :checked="!!view.exit_confirmation"
                :disabled="!open || !!store.busy"
                @change="store.setExitConfirmation($event.target.checked)"
              />
              <span>Equipment does not block exits or walkways</span>
            </label>
            <p class="mt-3 text-sm">{{ exitConfirmationText(view.exit_confirmation) }}</p>
            <p class="mt-2 text-xs font-bold text-ink/60">Adding or removing a line, changing a quantity or changing the venue clears this.</p>
            <p v-if="store.exitError" role="alert" class="mt-3 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">{{ store.exitError }}</p>
          </BauhausCard>

          <BauhausCard background="white" accent="none">
            <h2 class="text-2xl font-bold">History</h2>
            <p v-if="!view.history.length" class="mt-4 text-sm">Nothing recorded yet.</p>
            <ol v-else class="mt-4 flex flex-col gap-3">
              <li v-for="(entry, index) in view.history" :key="index" class="border-l-4 border-ink pl-3">
                <p class="text-sm font-bold">{{ historyEntryText(entry) }}</p>
                <p v-if="entry.detail" class="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{{ entry.detail }}</p>
                <p class="text-xs font-bold text-ink/60">{{ historyActor(entry) }} · {{ formatTechnicalTime(entry.created_at) }}</p>
              </li>
            </ol>
          </BauhausCard>
        </div>
      </div>
    </template>
  </main>
</template>
