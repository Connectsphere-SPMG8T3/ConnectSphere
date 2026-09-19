import { ref } from "vue";

export const toastState = ref(null);

let dismissTimer;

export function showToast(message, tone = "success", duration = 4000) {
  clearTimeout(dismissTimer);
  toastState.value = { message, tone };
  dismissTimer = setTimeout(dismissToast, duration);
}

export function dismissToast() {
  clearTimeout(dismissTimer);
  toastState.value = null;
}
