<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  label: {
    type: String,
    required: true,
  },
  options: {
    // [{ value, label }]
    type: Array,
    required: true,
  },
  placeholder: {
    type: String,
    default: "Any",
  },
});

defineEmits(["update:modelValue"]);

const selectId = `bauhaus-select-${Math.random().toString(36).slice(2, 10)}`;
</script>

<template>
  <div class="flex flex-col gap-2">
    <label :for="selectId" class="text-xs font-bold uppercase tracking-widest text-ink">
      {{ label }}
    </label>
    <select
      :id="selectId"
      :value="modelValue"
      class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium text-ink shadow-hard outline-none transition-colors focus:bg-bauhaus-yellow/20 sm:border-4"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option value="">{{ placeholder }}</option>
      <option v-for="option in props.options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </div>
</template>
