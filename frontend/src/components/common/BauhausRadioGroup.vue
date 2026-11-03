<script setup>
// A single-choice chip group (CR-108), styled like BauhausCheckboxGroup so the two read as a pair.
const props = defineProps({
  modelValue: {
    type: String,
    default: null,
  },
  label: {
    type: String,
    required: true,
  },
  required: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  options: {
    // [{ value, label, disabled? }]
    type: Array,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue"]);

const groupId = `bauhaus-radios-${Math.random().toString(36).slice(2, 10)}`;
</script>

<template>
  <fieldset class="flex flex-col gap-2" :disabled="props.disabled">
    <legend class="mb-2 text-xs font-bold text-ink">{{ label }}<span v-if="required" aria-hidden="true"> *</span></legend>
    <div class="flex flex-wrap gap-2">
      <label
        v-for="option in props.options"
        :key="option.value"
        class="inline-flex items-center gap-2 border-2 border-ink px-3 py-2 text-xs font-bold shadow-hard transition-colors"
        :class="[
          modelValue === option.value ? 'bg-bauhaus-yellow text-ink' : 'bg-canvas text-ink',
          props.disabled || option.disabled ? 'cursor-not-allowed' : 'cursor-pointer hover:bg-muted',
        ]"
      >
        <input
          :id="`${groupId}-${option.value}`"
          type="radio"
          class="h-4 w-4 accent-bauhaus-red"
          :name="groupId"
          :value="option.value"
          :checked="modelValue === option.value"
          :disabled="option.disabled"
          @change="emit('update:modelValue', option.value)"
        />
        {{ option.label }}
      </label>
    </div>
  </fieldset>
</template>
