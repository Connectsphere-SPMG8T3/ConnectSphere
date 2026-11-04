<script>
const ICONS = {
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5 20.5 7.5 8 20l-5 1 1-5Z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  block: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
  deactivate: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
  reactivate: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
};
</script>

<script setup>
// A small line icon that takes the colour and size of the text around it
// (`currentColor`, 1.25em). Square ends and corners, and circles only, to match
// the rest of the design system. Add a shape to ICONS to add an icon.
defineProps({
  name: { type: String, required: true, validator: (value) => value in ICONS },
});
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="square"
    stroke-linejoin="miter"
    class="h-[1.25em] w-[1.25em] shrink-0"
    aria-hidden="true"
    v-html="ICONS[name]"
  />
</template>
