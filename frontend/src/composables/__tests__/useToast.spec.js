import { beforeEach, describe, expect, it, vi } from "vitest";

import { dismissToast, showToast, toastState } from "@/composables/useToast";

describe("useToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    dismissToast();
  });

  it("shows a reusable success message and dismisses it automatically", () => {
    showToast("Draft saved");

    expect(toastState.value).toEqual({ message: "Draft saved", tone: "success" });

    vi.advanceTimersByTime(4000);

    expect(toastState.value).toBeNull();
    vi.useRealTimers();
  });
});