import { onBeforeUnmount, onMounted, ref } from "vue";

/**
 * Whether a CSS media query matches, kept up to date as the window resizes.
 * Use it only where CSS can't do the job, such as rendering one copy of a
 * control instead of hiding a second one. Without `matchMedia` (jsdom), it
 * reports `fallback`.
 */
export function useMediaQuery(query, fallback = true) {
  const list = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query) : null;
  const matches = ref(list ? list.matches : fallback);
  const update = (event) => {
    matches.value = event.matches;
  };
  onMounted(() => list?.addEventListener("change", update));
  onBeforeUnmount(() => list?.removeEventListener("change", update));
  return matches;
}
