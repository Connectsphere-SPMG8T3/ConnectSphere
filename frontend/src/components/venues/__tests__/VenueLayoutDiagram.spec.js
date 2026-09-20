import { createApp } from "vue";
import { describe, expect, it } from "vitest";

import VenueLayoutDiagram from "@/components/venues/VenueLayoutDiagram.vue";
import { LAYOUTS } from "@/features/venues/venueSearchStore";

function render(layout, label = "") {
  const el = document.createElement("div");
  document.body.appendChild(el);
  createApp(VenueLayoutDiagram, { layout, label }).mount(el);
  return el;
}

const signature = (el) =>
  [el.querySelectorAll("rect").length, el.querySelectorAll("circle").length].join(":");

describe("VenueLayoutDiagram", () => {
  it("draws every layout in the catalogue's controlled list", () => {
    for (const { value } of LAYOUTS) {
      const el = render(value);
      expect(el.querySelector("svg"), `${value} rendered nothing`).toBeTruthy();
    }
  });

  it("gives each layout its own arrangement, so none silently falls back to another", () => {
    const signatures = LAYOUTS.map(({ value }) => signature(render(value)));

    expect(new Set(signatures).size).toBe(LAYOUTS.length);
  });

  it("seats a theatre and leaves a reception standing", () => {
    // Circles are seats plus round tables; reception's are all tables.
    expect(render("theatre").querySelectorAll("circle").length).toBe(50);
    expect(render("reception").querySelectorAll("circle").length).toBe(6);
  });

  it("names the layout in the title and says it is not a floor plan", () => {
    const title = render("banquet", "Banquet").querySelector("title").textContent;

    expect(title).toContain("Banquet");
    expect(title).toContain("not this room's floor plan");
  });

  it("falls back to a drawable arrangement for an unknown layout rather than rendering nothing", () => {
    const el = render("mosh_pit");

    expect(el.querySelector("svg")).toBeTruthy();
    expect(el.querySelectorAll("circle").length).toBeGreaterThan(0);
  });
});
