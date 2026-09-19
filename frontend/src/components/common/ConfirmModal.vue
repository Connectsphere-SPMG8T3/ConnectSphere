<script setup>
import BauhausButton from "@/components/common/BauhausButton.vue";

const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: "Do you confirm you want to leave the page?",
  },
  message: {
    type: String,
    default: "Your changes will not be saved.",
  },
});

const emit = defineEmits(["confirm", "stay"]);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 px-4 py-6"
      role="presentation"
      @click.self="emit('stay')"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        class="w-full max-w-lg border-4 border-ink bg-canvas p-6 shadow-hard-lg sm:p-8"
      >
        <h2 id="confirm-modal-title" class="text-2xl font-black uppercase leading-tight tracking-tight">{{ props.title }}</h2>
        <p class="mt-4 text-base font-medium">{{ props.message }}</p>
        <div class="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <BauhausButton type="button" variant="outline" aria-label="Stay on page" @click="emit('stay')">Stay on page</BauhausButton>
          <BauhausButton type="button" variant="primary" aria-label="Confirm leave page" @click="emit('confirm')">Leave page</BauhausButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
