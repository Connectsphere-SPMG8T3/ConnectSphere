<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps({
  modelValue: {
    type: [String, Array],
    default: () => "",
  },
  label: {
    type: String,
    required: true,
  },
  required: {
    type: Boolean,
    default: false,
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
  showPlaceholder: {
    type: Boolean,
    default: true,
  },
  ariaLabel: {
    type: String,
    default: "",
  },
  multiple: {
    type: Boolean,
    default: false,
  },
  dropdown: {
    type: Boolean,
    default: false,
  },
  compact: {
    type: Boolean,
    default: false,
  },
  // A request to review this field (SCRUM-33), not a validation failure.
  flag: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:modelValue"]);

const selectId = `bauhaus-select-${Math.random().toString(36).slice(2, 10)}`;
const container = ref(null);
const isOpen = ref(false);
const selectedValues = computed(() => {
  if (Array.isArray(props.modelValue)) return props.modelValue;
  return props.modelValue ? [props.modelValue] : [];
});
const usesMenu = computed(() => props.multiple || props.dropdown);
const hasFlag = computed(() => Boolean(props.flag));
const flagId = `${selectId}-flag`;
const selectionLabel = computed(() => {
  if (!selectedValues.value.length) return props.placeholder;
  if (selectedValues.value.length === 1) {
    return props.options.find((option) => option.value === selectedValues.value[0])?.label || selectedValues.value[0];
  }
  return `${selectedValues.value.length} selected`;
});

function toggleOption(value) {
  const nextValues = selectedValues.value.includes(value)
    ? selectedValues.value.filter((selectedValue) => selectedValue !== value)
    : [...selectedValues.value, value];
  emit("update:modelValue", nextValues);
}

function selectOption(value) {
  emit("update:modelValue", value);
  isOpen.value = false;
}

function closeOnOutsideClick(event) {
  if (container.value && !container.value.contains(event.target)) isOpen.value = false;
}

onMounted(() => document.addEventListener("click", closeOnOutsideClick));
onBeforeUnmount(() => document.removeEventListener("click", closeOnOutsideClick));
</script>

<template>
  <div ref="container" class="flex flex-col gap-2">
    <label :for="selectId" class="text-xs font-bold uppercase tracking-widest text-ink">
      {{ label }}<span v-if="required" aria-hidden="true"> *</span>
    </label>
    <div v-if="usesMenu" class="relative">
      <button
        :id="selectId"
        type="button"
        :aria-label="ariaLabel || undefined"
        :aria-expanded="isOpen"
        aria-haspopup="listbox"
        :aria-describedby="hasFlag ? flagId : undefined"
        :data-flagged="hasFlag || undefined"
        class="flex w-full items-center justify-between border-2 border-ink px-4 py-3 text-left text-base font-medium text-ink outline-none transition-colors focus:bg-bauhaus-yellow/20"
        :class="[compact ? 'h-[50px] shadow-none' : 'shadow-hard sm:border-4', hasFlag ? 'bg-bauhaus-yellow/30' : 'bg-canvas']"
        @click.stop="isOpen = !isOpen"
      >
        <span class="truncate">{{ selectionLabel }}</span>
        <span
          aria-hidden="true"
          class="ml-3 h-2.5 w-2.5 shrink-0 rotate-45 border-b-2 border-r-2 border-ink transition-transform"
          :class="isOpen ? 'translate-y-1 rotate-[225deg]' : '-translate-y-0.5'"
        ></span>
      </button>
      <div v-if="isOpen" class="absolute left-0 right-0 z-20 mt-2 border-2 border-ink bg-canvas p-2 shadow-hard" role="listbox" :aria-label="label" :aria-multiselectable="multiple || undefined">
        <template v-for="option in props.options" :key="option.value">
          <label v-if="multiple" class="flex cursor-pointer items-center gap-3 px-2 py-2 text-sm font-bold hover:bg-bauhaus-yellow/20">
            <input
              type="checkbox"
              :value="option.value"
              :checked="selectedValues.includes(option.value)"
              class="h-4 w-4 accent-bauhaus-red"
              @change="toggleOption(option.value)"
            />
            <span>{{ option.label }}</span>
          </label>
          <button
            v-else
            type="button"
            role="option"
            :aria-selected="selectedValues.includes(option.value)"
            class="block w-full px-2 py-2 text-left text-sm font-bold hover:bg-bauhaus-yellow/20"
            @click="selectOption(option.value)"
          >
            {{ option.label }}
          </button>
        </template>
      </div>
    </div>
    <select
      v-else
      :id="selectId"
      :value="modelValue"
      :aria-required="required"
      :aria-label="ariaLabel || undefined"
      :aria-describedby="hasFlag ? flagId : undefined"
      :data-flagged="hasFlag || undefined"
      class="border-2 border-ink px-4 py-3 text-base font-medium text-ink outline-none transition-colors focus:bg-bauhaus-yellow/20"
      :class="[compact ? 'h-[50px] shadow-none' : 'shadow-hard sm:border-4', hasFlag ? 'bg-bauhaus-yellow/30' : 'bg-canvas']"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option v-if="showPlaceholder" value="">{{ placeholder }}</option>
      <option v-for="option in props.options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
    <p v-if="hasFlag" :id="flagId" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">
      {{ flag }}
    </p>
  </div>
</template>
