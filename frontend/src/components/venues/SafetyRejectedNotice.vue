<script setup>
import BauhausButton from "@/components/common/BauhausButton.vue";

defineProps({
  reason: { type: String, default: "" },
  canMarkRevised: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["mark-revised"]);
</script>

<template>
  <div class="mt-3 border-l-4 border-bauhaus-red pl-3" data-testid="venue-safety-rejected">
    <p class="inline-block bg-bauhaus-red px-2 py-0.5 text-xs font-black uppercase tracking-widest text-canvas">Safety rejected</p>
    <p class="mt-2 text-sm font-medium">{{ reason }}</p>
    <p class="mt-2 text-sm font-medium">Revise the arrangement with venue staff, then mark it revised and send the event for safety check again.</p>
    <BauhausButton v-if="canMarkRevised" class="mt-3" variant="secondary" :disabled="busy" @click="emit('mark-revised')">Mark as revised</BauhausButton>
  </div>
</template>
