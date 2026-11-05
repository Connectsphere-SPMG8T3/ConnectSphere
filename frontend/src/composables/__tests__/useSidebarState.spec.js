import { nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const STORAGE_KEY = "connectsphere.sidebarCollapsed";

// The state lives at module level, so each case loads a fresh copy.
async function load() {
  vi.resetModules();
  const { useSidebarState } = await import("@/composables/useSidebarState");
  return useSidebarState();
}

describe("useSidebarState", () => {
  beforeEach(() => localStorage.clear());

  it("starts collapsed when nothing has been saved", async () => {
    const { isCollapsed } = await load();
    expect(isCollapsed.value).toBe(true);
  });

  it("keeps a saved choice either way", async () => {
    localStorage.setItem(STORAGE_KEY, "false");
    expect((await load()).isCollapsed.value).toBe(false);

    localStorage.setItem(STORAGE_KEY, "true");
    expect((await load()).isCollapsed.value).toBe(true);
  });

  it("starts collapsed when storage can't be read", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect((await load()).isCollapsed.value).toBe(true);
    getItem.mockRestore();
  });

  it("never starts with the phone menu open", async () => {
    expect((await load()).isMobileOpen.value).toBe(false);
  });
});

describe("useSidebarState persistence", () => {
  beforeEach(() => localStorage.clear());

  it("saves a change of choice", async () => {
    const { isCollapsed } = await load();

    isCollapsed.value = false;
    await nextTick();

    expect(localStorage.getItem(STORAGE_KEY)).toBe("false");
  });

  it("keeps working when storage is blocked", async () => {
    const { isCollapsed } = await load();
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Blocked");
    });

    isCollapsed.value = false;
    await nextTick();

    expect(isCollapsed.value).toBe(false);
    setItem.mockRestore();
  });
});
