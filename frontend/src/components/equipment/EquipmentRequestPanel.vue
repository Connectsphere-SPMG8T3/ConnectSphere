<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  canRequestEquipment,
  canSubmit,
  emptyLine,
  inventoryWarning,
  quantityError,
  REQUEST_STATUS_LABELS,
  TECHNICAL_REQUIREMENTS_MAX_LENGTH,
  technicalRequirementsError,
} from "@/features/equipment/equipmentRequest";
import { useEquipmentRequestStore } from "@/features/equipment/equipmentRequestStore";

// SCRUM-45: the assigned coordinator's equipment request for one event.
const props = defineProps({
  eventId: { type: String, required: true },
  status: { type: String, required: true },
});

const store = useEquipmentRequestStore();
const draft = ref([emptyLine()]);
const isOpen = computed(() => canRequestEquipment(props.status));
const ready = computed(() => canSubmit(draft.value) && !store.isSubmitting);

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

const formatter = new Intl.DateTimeFormat("en-SG", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore" });

watch(
  () => props.eventId,
  (eventId) => {
    draft.value = [emptyLine()];
    store.load(eventId);
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

async function submit() {
  if (!ready.value) return;
  if (await store.submit(draft.value)) draft.value = [emptyLine()];
}
</script>

<template>
  <section aria-labelledby="equipment-request-title">
    <h2 id="equipment-request-title" class="mb-2 text-2xl font-black uppercase tracking-tight">Equipment request</h2>
    <p class="mb-6 text-sm font-medium text-ink/70">Lines go to Technical Support as Pending. They check availability for the event's dates.</p>

    <p v-if="store.isLoading && !store.lines.length" class="text-sm font-bold uppercase tracking-widest text-ink/70" role="status">
      Loading equipment…
    </p>
    <p v-else-if="store.error" role="alert" class="border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas">
      {{ store.error }}
    </p>
    <BauhausEmptyState
      v-else-if="!store.lines.length"
      title="No equipment requested yet"
      :detail="isOpen ? 'Add items from the catalogue below.' : ''"
    />
    <ul v-else class="space-y-3">
      <li v-for="line in store.lines" :key="line.id" class="border-2 border-ink p-4">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <span class="font-black uppercase tracking-tight">{{ line.equipment_name }} <span class="font-bold">× {{ line.quantity }}</span></span>
          <span class="border-2 border-ink px-3 py-1 text-[10px] font-bold uppercase tracking-widest" :class="STATUS_BADGE_CLASSES[line.status]">
            {{ REQUEST_STATUS_LABELS[line.status] ?? line.status }}
          </span>
        </div>
        <p v-if="line.technical_requirements" class="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm font-medium">{{ line.technical_requirements }}</p>
        <p class="mt-2 text-xs font-bold text-ink/60">
          {{ line.requested_by?.full_name ?? "Unknown user" }} · {{ formatter.format(new Date(line.created_at)) }}
        </p>
      </li>
    </ul>

    <form v-if="isOpen" class="mt-8 space-y-6" novalidate @submit.prevent="submit">
      <h3 class="text-sm font-bold uppercase tracking-widest">Add items</h3>
      <fieldset v-for="(line, index) in draft" :key="index" class="min-w-0 space-y-4 border-2 border-ink p-4">
        <legend class="px-1 text-xs font-bold uppercase tracking-widest">Item {{ index + 1 }}</legend>
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
            <p v-if="duplicateMessages[index]" class="mt-2 text-xs font-bold uppercase tracking-wide text-bauhaus-red">
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
          <label :for="`technical-requirements-${index}`" class="block text-xs font-bold uppercase tracking-widest">
            Technical requirements <span class="font-medium normal-case tracking-normal text-ink/60">(optional)</span>
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
  </section>
</template>
