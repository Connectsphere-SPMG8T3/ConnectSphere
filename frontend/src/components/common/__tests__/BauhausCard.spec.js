import { createApp, h, nextTick } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BauhausCard from "@/components/common/BauhausCard.vue";

async function mountCard(props, child = "input") {
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(() => h(BauhausCard, props, () => h(child))).mount(el);
  await nextTick();
  return { card: el.firstElementChild, field: el.querySelector(child) };
}

function pressEnter(target) {
  const event = new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
  target.dispatchEvent(event);
  return event;
}

describe("BauhausCard", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  // Cancelling a bubbled Enter stops the browser submitting the form the card
  // wraps (the login form), a textarea taking a new line, and a focused button
  // inside the card being pressed from the keyboard.
  it.each(["input", "textarea", "button"])("leaves Enter pressed in a %s inside the card to the browser", async (child) => {
    const { field } = await mountCard({}, child);

    expect(pressEnter(field).defaultPrevented).toBe(false);
  });

  it("does not activate a clickable card when Enter is pressed in a field inside it", async () => {
    const onClick = vi.fn();
    const { field } = await mountCard({ clickable: true, onClick });

    const event = pressEnter(field);

    expect(onClick).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("is white with its tone's stripe by default", async () => {
    const { card } = await mountCard({ background: "red" }, "p");
    expect(card.className).toContain("bg-surface");
    expect(card.querySelector("span[aria-hidden]").className).toContain("bg-bauhaus-red");
  });

  it("supports a green status stripe", async () => {
    const { card } = await mountCard({ background: "green" }, "p");
    expect(card.querySelector("span[aria-hidden]").className).toContain("bg-bauhaus-green");
  });

  it("greys out when dimmed: grey fill, faded text and a grey stripe whatever its tone", async () => {
    const { card } = await mountCard({ background: "red", dimmed: true }, "p");
    expect(card.className).toContain("bg-muted");
    expect(card.className).toContain("text-ink/70");
    expect(card.className).not.toContain("bg-surface");
    const stripe = card.querySelector("span[aria-hidden]");
    expect(stripe.className).toContain("bg-ink/30");
    expect(stripe.className).not.toContain("bg-bauhaus-red");
  });

  it("activates a focused clickable card on Enter", async () => {
    const onClick = vi.fn();
    const { card } = await mountCard({ clickable: true, onClick });

    pressEnter(card);

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
