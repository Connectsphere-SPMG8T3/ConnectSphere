<script setup>
const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
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
  // A request to review this field (SCRUM-33), not a validation failure.
  flag: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:modelValue"]);

const groupId = `bauhaus-checks-${Math.random().toString(36).slice(2, 10)}`;
const flagId = `${groupId}-flag`;

function toggle(value, checked) {
  const next = props.modelValue.filter((entry) => entry !== value);
  if (checked) next.push(value);
  emit("update:modelValue", next);
}
</script>

<template>
  <fieldset
    class="flex flex-col gap-2"
    :class="props.flag ? 'bg-bauhaus-yellow/30 p-2' : ''"
    :aria-describedby="props.flag ? flagId : undefined"
    :data-flagged="props.flag ? 'true' : undefined"
  >
    <legend class="mb-2 text-xs font-bold uppercase tracking-widest text-ink">{{ label }}<span v-if="required" aria-hidden="true"> *</span></legend>
    <div class="flex flex-wrap gap-2">
      <label
        v-for="option in props.options"
        :key="option.value"
        class="inline-flex cursor-pointer items-center gap-2 border-2 border-ink px-3 py-2 text-xs font-bold uppercase tracking-wide shadow-hard transition-colors"
        :class="modelValue.includes(option.value) ? 'bg-bauhaus-yellow text-ink' : 'bg-canvas text-ink'"
      >
        <input
          :id="`${groupId}-${option.value}`"
          type="checkbox"
          class="h-4 w-4 accent-bauhaus-red"
          :value="option.value"
          :checked="modelValue.includes(option.value)"
          @change="toggle(option.value, $event.target.checked)"
        />
        {{ option.label }}
      </label>
    </div>
    <p v-if="props.flag" :id="flagId" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">
      {{ props.flag }}
    </p>
  </fieldset>
</template>
