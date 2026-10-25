<script setup>
/**
 * Story 37 AC6, Q20: a booking or equipment line an approved change marked Needs
 * re-review, why, and the coordinator's Send for re-review with an optional note.
 * The page decides what it is and who gets it; this only draws it.
 */
import { ref } from "vue";
import BauhausButton from "@/components/common/BauhausButton.vue";

const props = defineProps({
  reason: { type: String, default: "" },
  // Who it goes to, for the button: "venue staff" or "technical support".
  recipients: { type: String, required: true },
  busy: { type: Boolean, default: false },
});
const emit = defineEmits(["send"]);
const sending = ref(false);
const note = ref("");

function send() {
  if (props.busy || note.value.trim().length > 1000) return;
  emit("send", note.value.trim() || null);
  sending.value = false;
}
</script>

<template>
  <div class="mt-3 border-l-4 border-bauhaus-yellow pl-3" data-testid="needs-re-review">
    <p class="inline-block border-2 border-ink bg-bauhaus-yellow px-2 py-0.5 text-xs font-bold">Needs re-review</p>
    <p v-if="reason" class="mt-2 text-sm font-medium">{{ reason }}</p>
    <p class="mt-2 text-sm font-medium">It stays held until {{ recipients }} decide.</p>
    <BauhausButton v-if="!sending" class="mt-3" variant="secondary" :disabled="busy" @click="sending = true; note = ''">
      Send for re-review
    </BauhausButton>
    <section v-else role="dialog" aria-label="Send for re-review" class="mt-4 border-2 border-ink p-4">
      <h3 class="text-lg font-bold">Send for re-review</h3>
      <label class="mt-3 block text-sm font-bold">
        Note for {{ recipients }} (optional)
        <textarea v-model="note" maxlength="1000" :disabled="busy" rows="3"
          class="mt-2 block w-full border-2 border-ink bg-canvas p-3 font-medium" />
      </label>
      <p class="mt-1 text-sm">{{ note.length }} / 1000</p>
      <div class="mt-4 flex flex-col gap-3 sm:flex-row">
        <BauhausButton variant="secondary" :disabled="busy" @click="send">Send to {{ recipients }}</BauhausButton>
        <BauhausButton variant="outline" :disabled="busy" @click="sending = false">Cancel</BauhausButton>
      </div>
    </section>
  </div>
</template>
