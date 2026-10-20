<script setup>
import { ref } from "vue";
import BauhausButton from "@/components/common/BauhausButton.vue";

const props = defineProps({
  reason: { type: String, default: "" },
  canMarkRevised: { type: Boolean, default: false },
  canReplace: { type: Boolean, default: false },
  replacement: { type: Object, default: null },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["mark-revised", "replace"]);
const revising = ref(false);
const note = ref("");

function markRevised() {
  if (!props.busy && note.value.trim() && note.value.trim().length <= 1000) {
    emit("mark-revised", note.value.trim());
  }
}
</script>

<template>
  <div class="mt-3 border-l-4 border-bauhaus-red pl-3" data-testid="venue-safety-rejected">
    <p class="inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-black uppercase tracking-widest text-canvas">Safety rejected</p>
    <p class="mt-2 text-sm font-medium">{{ reason }}</p>
    <p class="mt-2 text-sm font-medium">Revise the arrangement with venue staff and mark it revised, or replace the venue. Then send the event for safety check again.</p>
    <p v-if="replacement" class="mt-3 text-sm font-bold">Replacement requested: {{ replacement.venue_name ?? 'another venue' }}</p>
    <template v-else>
      <div v-if="!revising" class="mt-3 flex flex-col gap-3 sm:flex-row">
        <BauhausButton v-if="canMarkRevised" variant="secondary" :disabled="busy" @click="revising = true; note = ''">Mark as revised</BauhausButton>
        <BauhausButton v-if="canReplace" variant="outline" :disabled="busy" @click="emit('replace')">Replace venue</BauhausButton>
      </div>
      <section v-if="revising && canMarkRevised" role="dialog" aria-label="Mark as revised" class="mt-4 border-2 border-ink p-4">
        <h3 class="text-lg font-black uppercase">Mark as revised</h3>
        <label class="mt-3 block text-sm font-bold">
          What changed, or what should the Safety Officer know?
          <textarea v-model="note" maxlength="1000" required :disabled="busy" rows="4" class="mt-2 block w-full border-2 border-ink bg-canvas p-3 font-medium" />
        </label>
        <p class="mt-1 text-sm">{{ note.length }} / 1000</p>
        <div class="mt-4 flex flex-col gap-3 sm:flex-row">
          <BauhausButton variant="secondary" :disabled="busy || !note.trim() || note.trim().length > 1000" @click="markRevised">Mark as revised</BauhausButton>
          <BauhausButton variant="outline" :disabled="busy" @click="revising = false">Cancel</BauhausButton>
        </div>
      </section>
    </template>
  </div>
</template>
