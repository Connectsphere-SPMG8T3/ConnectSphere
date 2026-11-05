import { createApp, h } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMediaQuery } from "@/composables/useMediaQuery";

function mounted(query) {
  let matches;
  const app = createApp({
    setup() {
      matches = useMediaQuery(query);
      return () => h("div");
    },
  });
  app.mount(document.createElement("div"));
  return { matches, app };
}

describe("useMediaQuery", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("follows the query as the window changes, and stops listening on unmount", () => {
    const list = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
    vi.stubGlobal("matchMedia", vi.fn(() => list));

    const { matches, app } = mounted("(min-width: 640px)");
    expect(window.matchMedia).toHaveBeenCalledWith("(min-width: 640px)");
    expect(matches.value).toBe(false);

    const [, listener] = list.addEventListener.mock.calls[0];
    listener({ matches: true });
    expect(matches.value).toBe(true);

    app.unmount();
    expect(list.removeEventListener).toHaveBeenCalledWith("change", listener);
  });
});
