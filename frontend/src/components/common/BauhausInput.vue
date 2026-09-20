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
  required: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: "text",
  },
  placeholder: {
    type: String,
    default: "",
  },
  min: {
    type: String,
    default: undefined,
  },
  error: {
    type: String,
    default: "",
  },
  autocomplete: {
    type: String,
    default: "off",
  },
  ariaLabel: {
    type: String,
    default: "",
  },
  compact: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["update:modelValue"]);

const inputId = `bauhaus-input-${Math.random().toString(36).slice(2, 10)}`;
const hasError = computed(() => Boolean(props.error));
</script>

<template>
  <div class="flex flex-col gap-2">
    <label :for="inputId" class="text-xs font-bold uppercase tracking-widest text-ink">
      {{ label }}<span v-if="required" aria-hidden="true"> *</span>
    </label>
    <input
      :id="inputId"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :min="min"
      :aria-required="required"
      :aria-label="ariaLabel || undefined"
      :autocomplete="autocomplete"
      :aria-invalid="hasError"
      :aria-describedby="hasError ? `${inputId}-error` : undefined"
      class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium text-ink outline-none transition-colors placeholder:text-ink/40 focus:bg-bauhaus-yellow/20"
      :class="[compact ? 'h-[50px] shadow-none' : 'shadow-hard sm:border-4', hasError ? 'border-bauhaus-red' : 'border-ink']"
      @input="$emit('update:modelValue', $event.target.value)"
    />
    <p v-if="hasError" :id="`${inputId}-error`" class="text-xs font-bold uppercase tracking-wide text-bauhaus-red">
      {{ error }}
    </p>
  </div>
</template>
