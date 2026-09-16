import { ref, watch } from "vue";

const STORAGE_KEY = "connectsphere.sidebarCollapsed";

function loadInitial() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

const isCollapsed = ref(loadInitial());

watch(isCollapsed, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, String(value));
  } catch {
    // localStorage may be unavailable (private browsing) — collapse state
    // simply won't survive a reload in that case.
  }
});

export function useSidebarState() {
  return { isCollapsed };
}
