import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createPoller, POLL_INTERVAL_MS } from "@/features/notifications/polling";

function setVisibility(state) {
  Object.defineProperty(document, "visibilityState", { value: state, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("createPoller (ADR-0004)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls every 10 seconds", () => {
    expect(POLL_INTERVAL_MS).toBe(10_000);
  });

  it("ticks at once on start, then once per interval", async () => {
    const tick = vi.fn().mockResolvedValue();
    const poller = createPoller({ tick });
    poller.start();
    expect(tick).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2);

    expect(tick).toHaveBeenCalledTimes(3);
    poller.stop();
  });

  it("skips a tick while the previous one is still running", async () => {
    let release;
    const tick = vi.fn(() => new Promise((resolve) => { release = resolve; }));
    const poller = createPoller({ tick });
    poller.start();

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    expect(tick).toHaveBeenCalledTimes(1);

    release();
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(tick).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("does not tick while the tab is hidden, and ticks at once when it is visible again", async () => {
    const tick = vi.fn().mockResolvedValue();
    const poller = createPoller({ tick });
    poller.start();
    setVisibility("hidden");
    tick.mockClear();

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    expect(tick).not.toHaveBeenCalled();

    setVisibility("visible");
    await vi.advanceTimersByTimeAsync(0);
    expect(tick).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("keeps polling after a tick fails", async () => {
    const tick = vi.fn().mockRejectedValueOnce(new Error("503")).mockResolvedValue();
    const poller = createPoller({ tick });
    poller.start();
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);

    expect(tick).toHaveBeenCalledTimes(2);
    poller.stop();
  });

  it("starting twice does not double the polling", async () => {
    const tick = vi.fn().mockResolvedValue();
    const poller = createPoller({ tick });
    poller.start();
    poller.start();
    tick.mockClear();

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);

    expect(tick).toHaveBeenCalledTimes(1);
    poller.stop();
  });

  it("stopping a poller that never started is harmless", () => {
    const poller = createPoller({ tick: vi.fn() });

    expect(() => poller.stop()).not.toThrow();
  });

  it("stop() clears the timer and the visibility listener", async () => {
    const tick = vi.fn().mockResolvedValue();
    const poller = createPoller({ tick });
    poller.start();
    poller.stop();
    tick.mockClear();

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    setVisibility("hidden");
    setVisibility("visible");
    await vi.advanceTimersByTimeAsync(0);

    expect(tick).not.toHaveBeenCalled();
  });
});
