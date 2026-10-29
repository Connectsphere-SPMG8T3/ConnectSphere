<script setup>
import { computed, ref } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import {
  canSaveLine,
  changeNotice,
  inventoryWarning,
  lineToDraft,
  quantityError,
  TECHNICAL_REQUIREMENTS_MAX_LENGTH,
  technicalRequirementsError,
} from "@/features/equipment/equipmentRequest";

// SCRUM-44 AC2: change one recorded line's item, quantity or technical
// requirements, with the same fields and rules as adding it (SCRUM-45).
const props = defineProps({
  line: { type: Object, required: true },
  catalogue: { type: Array, required: true },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["save", "cancel"]);

const draft = ref(lineToDraft(props.line));
const catalogueById = computed(() => Object.fromEntries(props.catalogue.map((item) => [item.equipment_id, item])));
const options = computed(() =>
  props.catalogue.map((item) => ({ value: item.equipment_id, label: `${item.name} (${item.total_quantity} in catalogue)` })),
);
const shownQuantityError = computed(() =>
  String(draft.value.quantity ?? "").trim() === "" ? "" : quantityError(draft.value.quantity) ?? "",
);
const notice = computed(() => changeNotice(props.line.status));
const ready = computed(() => canSaveLine(draft.value) && !props.busy);

function save() {
  if (ready.value) emit("save", { ...draft.value });
}
</script>

<template>
  <form class="mt-4 min-w-0 space-y-4 border-t-2 border-ink pt-4" novalidate @submit.prevent="save">
    <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
      <BauhausSelect
        v-model="draft.equipmentId"
        class="min-w-0"
        label="Item"
        required
        compact
        placeholder="Choose an item"
        :options="options"
      />
      <BauhausInput
        v-model="draft.quantity"
        class="min-w-0"
        label="Quantity"
        type="number"
        min="1"
        required
        compact
        :error="shownQuantityError"
        :flag="inventoryWarning(catalogueById[draft.equipmentId], draft.quantity)"
      />
    </div>
    <div>
      <label :for="`edit-requirements-${line.id}`" class="block text-xs font-bold">
        Technical requirements <span class="font-medium text-ink/60">(optional)</span>
      </label>
      <textarea
        :id="`edit-requirements-${line.id}`"
        v-model="draft.technicalRequirements"
        rows="2"
        :maxlength="TECHNICAL_REQUIREMENTS_MAX_LENGTH"
        class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
      ></textarea>
      <div class="mt-1 flex items-center justify-between gap-4">
        <p class="text-xs font-bold text-bauhaus-red">{{ technicalRequirementsError(draft.technicalRequirements) }}</p>
        <p class="text-xs font-bold text-ink/70">{{ (draft.technicalRequirements ?? "").length }} / {{ TECHNICAL_REQUIREMENTS_MAX_LENGTH }}</p>
      </div>
    </div>
    <p v-if="notice" class="text-sm font-bold">{{ notice }}</p>
    <div class="flex flex-wrap gap-3">
      <BauhausButton type="submit" variant="secondary" :aria-label="`Save changes to ${line.equipment_name}`" :disabled="!ready">
        {{ busy ? "Saving…" : "Save changes" }}
      </BauhausButton>
      <BauhausButton variant="outline" aria-label="Cancel" :disabled="busy" @click="emit('cancel')">Cancel</BauhausButton>
    </div>
  </form>
</template>
