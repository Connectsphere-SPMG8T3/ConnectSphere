<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  label: {
    type: String,
    required: true,
  },
  type: {
    type: String,
    default: "text",
  },
  placeholder: {
    type: String,
    default: "",
  },
  error: {
    type: String,
    default: "",
  },
  autocomplete: {
    type: String,
    default: "off",
  },
});

defineEmits(["update:modelValue"]);

const inputId = `bauhaus-input-${Math.random().toString(36).slice(2, 10)}`;
const hasError = computed(() => Boolean(props.error));
</script>

<template>
  <div class="flex flex-col gap-2">
    <label :for="inputId" class="text-xs font-bold uppercase tracking-widest text-ink">
      {{ label }}
    </label>
    <input
      :id="inputId"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      :aria-invalid="hasError"
      :aria-describedby="hasError ? `${inputId}-error` : undefined"
      class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium text-ink shadow-hard outline-none transition-colors placeholder:text-ink/40 focus:bg-bauhaus-yellow/20 sm:border-4"
      :class="hasError ? 'border-bauhaus-red' : 'border-ink'"
      @input="$emit('update:modelValue', $event.target.value)"
    />
    <p v-if="hasError" :id="`${inputId}-error`" class="text-xs font-bold uppercase tracking-wide text-bauhaus-red">
      {{ error }}
    </p>
  </div>
</template>
