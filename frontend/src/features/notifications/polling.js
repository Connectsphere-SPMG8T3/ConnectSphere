// ADR-0004: poll the API every 10 seconds while the tab is visible. One constant,
// so changing the interval is a one-line change.
export const POLL_INTERVAL_MS = 10_000;

/**
 * Runs `tick` now, then every `intervalMs`, but only while the tab is visible.
 * A tick is skipped while the previous one is still running, and a failed tick
 * never stops the polling (the store decides what a failure means). Becoming
 * visible again ticks at once, so a returning user never waits out the interval.
 */
export function createPoller({
  tick,
  intervalMs = POLL_INTERVAL_MS,
  isVisible = () => document.visibilityState === "visible",
}) {
  let timer = null;
  let inFlight = false;

  async function run() {
    if (inFlight || !isVisible()) return;
    inFlight = true;
    try {
      await tick();
    } catch {
      // The next tick tries again.
    } finally {
      inFlight = false;
    }
  }

  function onVisibilityChange() {
    run();
  }

  return {
    start() {
      if (timer !== null) return;
      timer = setInterval(run, intervalMs);
      document.addEventListener("visibilitychange", onVisibilityChange);
      run();
    },
    stop() {
      if (timer === null) return;
      clearInterval(timer);
      timer = null;
      document.removeEventListener("visibilitychange", onVisibilityChange);
    },
  };
}
