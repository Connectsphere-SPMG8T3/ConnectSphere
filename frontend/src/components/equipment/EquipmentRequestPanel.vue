<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import EquipmentLineEditForm from "@/components/equipment/EquipmentLineEditForm.vue";
import TechnicalHistoryList from "@/components/equipment/TechnicalHistoryList.vue";
import ReReviewNotice from "@/components/events/ReReviewNotice.vue";
import {
  canChangeLine,
  canRequestEquipment,
  canSubmit,
  emptyLine,
  inventoryWarning,
  liveLines,
  quantityError,
  removeNotice,
  REQUEST_STATUS_LABELS,
  TECHNICAL_REQUIREMENTS_MAX_LENGTH,
  technicalRequirementsError,
} from "@/features/equipment/equipmentRequest";
import { formatSingaporeDateTime } from "@/features/venues/singaporeTime";
import { useEquipmentRequestStore } from "@/features/equipment/equipmentRequestStore";
import {
  exitConfirmationText,
  hasLiveLines,
  TECHNICAL_STATUS_BADGE_CLASSES,
  TECHNICAL_STATUS_LABELS,
} from "@/features/equipment/technical";

// SCRUM-45: the assigned coordinator's equipment request for one event.
// SCRUM-24 AC9: with each line's status, Technical Support's reason and notes,
// the event's technical status and the exit check.
// SCRUM-44: while the event is in planning each line can be changed or removed;
// removed lines leave the list and stay in the equipment history (AC8).
const props = defineProps({
  eventId: { type: String, required: true },
  status: { type: String, required: true },
});

const store = useEquipmentRequestStore();
const draft = ref([emptyLine()]);
const isOpen = computed(() => canRequestEquipment(props.status));
const ready = computed(() => canSubmit(draft.value) && !store.isSubmitting);
const shownLines = computed(() => liveLines(store.lines));
const editingLineId = ref(null);
const removing = ref(null);

const catalogueById = computed(() => Object.fromEntries(store.catalogue.map((item) => [item.equipment_id, item])));
const options = computed(() =>
  store.catalogue.map((item) => ({ value: item.equipment_id, label: `${item.name} (${item.total_quantity} in catalogue)` })),
);

// Only a later line naming an item already listed is marked, so the first stays clean.
const duplicateMessages = computed(() => {
  const seen = new Set();
  return draft.value.map(({ equipmentId }) => {
    if (!equipmentId) return "";
    if (seen.has(equipmentId)) {
      return `${catalogueById.value[equipmentId]?.name ?? "This item"} is already on this request. Combine the quantities.`;
    }
    seen.add(equipmentId);
    return "";
  });
});

// Static class names: Tailwind can't see built ones.
const STATUS_BADGE_CLASSES = {
  pending: "bg-bauhaus-yellow text-ink",
  reserved: "bg-bauhaus-blue text-canvas",
  rejected: "bg-bauhaus-red text-canvas",
  re_review: "bg-bauhaus-yellow text-ink",
  released: "bg-canvas text-ink",
};

watch(
  () => props.eventId,
  (eventId) => {
    draft.value = [emptyLine()];
    editingLineId.value = null;
    removing.value = null;
    store.load(eventId);
    store.loadHistory(eventId);
  },
  { immediate: true },
);

function shownQuantityError(line) {
  return String(line.quantity ?? "").trim() === "" ? "" : quantityError(line.quantity) ?? "";
}

function addLine() {
  draft.value.push(emptyLine());
}

function removeLine(index) {
  draft.value.splice(index, 1);
  if (!draft.value.length) draft.value.push(emptyLine());
}

async function saveLine(line, lineDraft) {
  if (await store.updateLine(line, lineDraft)) editingLineId.value = null;
}

async function confirmRemove() {
  const line = removing.value;
  removing.value = null;
  if (line) await store.removeLine(line);
}

async function submit() {
  if (!ready.value) return;
  if (await store.submit(draft.value)) draft.value = [emptyLine()];
}
</script>

<template>
  <section aria-labelledby="equipment-request-title">
    <h2 id="equipment-request-title" class="mb-2 text-2xl font-bold">Equipment request</h2>
    <p class="mb-6 text-sm font-medium text-ink/70">Lines go to Technical Support as Pending. They check availability for the event's dates.</p>

    <dl v-if="store.technicalStatus" class="mb-6 grid gap-3 border-2 border-ink p-4 sm:grid-cols-2">
      <div>
        <dt class="text-xs font-bold">Technical status</dt>
        <dd class="mt-1">
          <span class="inline-block border-2 border-ink px-3 py-1 text-xs font-bold" :class="TECHNICAL_STATUS_BADGE_CLASSES[store.technicalStatus]">
            {{ TECHNICAL_STATUS_LABELS[store.technicalStatus] ?? store.technicalStatus }}
          </span>
        </dd>
      </div>
      <div v-if="hasLiveLines(store.lines)">
        <dt class="text-xs font-bold">Exits and walkways clear</dt>
        <dd class="mt-1 text-sm">{{ exitConfirmationText(store.exitConfirmation) }}</dd>
      </div>
    </dl>

    <p v-if="store.actionError" role="alert" class="mb-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
      {{ store.actionError }}
    </p>
    <p v-if="store.isLoading && !store.lines.length" class="text-sm font-bold text-ink/70" role="status">
      Loading equipment…
    </p>
    <p v-else-if="store.error" role="alert" class="border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
      {{ store.error }}
    </p>
    <BauhausEmptyState
      v-else-if="!shownLines.length"
      title="No equipment requested yet"
      :detail="isOpen ? 'Add items from the catalogue below.' : ''"
    />
    <ul v-else class="space-y-3">
      <li v-for="line in shownLines" :key="line.id" data-testid="equipment-line" class="border-2 border-ink p-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <span class="font-bold">{{ line.equipment_name }} <span class="font-bold">× {{ line.quantity }}</span></span>
          <span class="border-2 border-ink px-3 py-1 text-xs font-bold" :class="STATUS_BADGE_CLASSES[line.status]">
            {{ REQUEST_STATUS_LABELS[line.status] ?? line.status }}
          </span>
        </div>
        <p v-if="line.technical_requirements" class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm font-medium">{{ line.technical_requirements }}</p>
        <p v-if="line.not_available_reason" class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">
          <span class="font-bold">Not available:</span> {{ line.not_available_reason }}
        </p>
        <ReReviewNotice
          v-if="line.needs_re_review_reason"
          :reason="line.needs_re_review_reason"
          recipients="technical support"
          :busy="store.isSubmitting"
          @send="(note) => store.sendForReReview(line.id, note)"
        />
        <p v-if="line.status === 're_review'" class="mt-2 text-sm font-bold">Technical Support are re-checking this line. Its reservation is kept meanwhile.</p>
        <p v-if="line.technical_notes" class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] border-l-4 border-bauhaus-blue pl-2 text-sm">
          <span class="font-bold">Technical Support notes:</span> {{ line.technical_notes }}
        </p>
        <p class="mt-2 text-xs font-bold text-ink/60">
          {{ line.requested_by?.full_name ?? "Unknown user" }} · {{ formatSingaporeDateTime(line.created_at) }}
        </p>
        <EquipmentLineEditForm
          v-if="editingLineId === line.id"
          :line="line"
          :catalogue="store.catalogue"
          :busy="store.busyLineId === line.id"
          @save="(lineDraft) => saveLine(line, lineDraft)"
          @cancel="editingLineId = null"
        />
        <div v-else-if="canChangeLine(status, line.status)" class="mt-4 flex flex-wrap gap-3">
          <BauhausButton
            variant="outline"
            :aria-label="`Edit ${line.equipment_name}`"
            :disabled="!!store.busyLineId"
            @click="editingLineId = line.id"
          >
            Edit
          </BauhausButton>
          <BauhausButton
            variant="outline"
            :aria-label="`Remove ${line.equipment_name} from the request`"
            :disabled="!!store.busyLineId"
            @click="removing = line"
          >
            {{ store.busyLineId === line.id ? "Removing…" : "Remove" }}
          </BauhausButton>
        </div>
      </li>
    </ul>
    <p v-if="!isOpen && shownLines.length" class="mt-4 text-sm font-medium text-ink/70">Equipment can only be changed while the event is in Planning.</p>

    <ConfirmModal
      :open="!!removing"
      :title="removing ? `Remove ${removing.quantity} × ${removing.equipment_name}?` : ''"
      :message="removing ? removeNotice(removing.status) : ''"
      confirm-label="Remove line"
      cancel-label="Keep line"
      @confirm="confirmRemove"
      @stay="removing = null"
    />

    <form v-if="isOpen" class="mt-8 space-y-6" novalidate @submit.prevent="submit">
      <h3 class="text-sm font-bold">Add items</h3>
      <fieldset v-for="(line, index) in draft" :key="index" class="min-w-0 space-y-4 border-2 border-ink p-4">
        <legend class="px-1 text-xs font-bold">Item {{ index + 1 }}</legend>
        <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <div class="min-w-0">
            <BauhausSelect
              v-model="line.equipmentId"
              label="Item"
              required
              compact
              placeholder="Choose an item"
              :options="options"
            />
            <p v-if="duplicateMessages[index]" class="mt-2 text-xs font-bold text-bauhaus-red">
              {{ duplicateMessages[index] }}
            </p>
          </div>
          <BauhausInput
            class="min-w-0"
            v-model="line.quantity"
            label="Quantity"
            type="number"
            min="1"
            required
            compact
            :error="shownQuantityError(line)"
            :flag="inventoryWarning(catalogueById[line.equipmentId], line.quantity)"
          />
        </div>
        <div>
          <label :for="`technical-requirements-${index}`" class="block text-xs font-bold">
            Technical requirements <span class="font-medium text-ink/60">(optional)</span>
          </label>
          <textarea
            :id="`technical-requirements-${index}`"
            v-model="line.technicalRequirements"
            rows="2"
            :maxlength="TECHNICAL_REQUIREMENTS_MAX_LENGTH"
            class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
          ></textarea>
          <div class="mt-1 flex items-center justify-between gap-4">
            <p class="text-xs font-bold text-bauhaus-red">{{ technicalRequirementsError(line.technicalRequirements) }}</p>
            <p class="text-xs font-bold text-ink/70">{{ (line.technicalRequirements ?? "").length }} / {{ TECHNICAL_REQUIREMENTS_MAX_LENGTH }}</p>
          </div>
        </div>
        <BauhausButton
          v-if="draft.length > 1"
          variant="outline"
          :aria-label="`Remove item ${index + 1}`"
          @click="removeLine(index)"
        >
          Remove
        </BauhausButton>
      </fieldset>

      <p v-if="store.submitError" role="alert" class="border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
        {{ store.submitError }}
      </p>

      <div class="flex flex-wrap gap-3">
        <BauhausButton variant="outline" aria-label="Add another item" @click="addLine">Add another item</BauhausButton>
        <BauhausButton type="submit" variant="secondary" aria-label="Submit equipment request" :disabled="!ready">
          {{ store.isSubmitting ? "Submitting…" : "Submit request" }}
        </BauhausButton>
      </div>
    </form>
    <p v-else class="mt-6 text-sm font-medium text-ink/70">New equipment can only be requested while the event is in planning.</p>

    <section v-if="store.history.length || store.historyError" class="mt-8" aria-labelledby="equipment-history-title">
      <h3 id="equipment-history-title" class="text-sm font-bold">Technical preparation history</h3>
      <p v-if="store.historyError" role="status" class="mt-4 text-sm font-medium">The equipment history couldn't be loaded.</p>
      <TechnicalHistoryList v-else :entries="store.history" />
    </section>
  </section>
</template>
