import { ref, watch } from "vue";

const STORAGE_KEY = "connectsphere.sidebarCollapsed";

// Collapsed until the user expands it; a saved choice wins either way.
function loadInitial() {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

const isCollapsed = ref(loadInitial());

// Whether the sidebar is showing over the page on narrow screens. Deliberately
// not persisted — every page load starts with the page, not the menu. It lives
// here rather than in Nav because the button that opens it sits in TopBar.
const isMobileOpen = ref(false);

watch(isCollapsed, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, String(value));
  } catch {
    // localStorage may be unavailable (private browsing) — collapse state
    // simply won't survive a reload in that case.
  }
});

export function useSidebarState() {
  return { isCollapsed, isMobileOpen };
}
