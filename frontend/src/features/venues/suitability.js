// How a venue's suitability verdict (REQUIREMENTS §6.11, SCRUM-18) is shown.
// Classes are full static names so Tailwind's scanner sees them.
const BADGES = {
  suitable: { text: "Suitable", classes: "bg-canvas text-ink" },
  suitable_with_warnings: { text: "Suitable with warnings", classes: "bg-bauhaus-yellow text-ink" },
  unsuitable: { text: "Unsuitable", classes: "bg-bauhaus-red text-canvas" },
};

// Null when the search named no event: there is nothing to be suitable for.
export function suitabilityBadge(suitability) {
  return suitability ? (BADGES[suitability.verdict] ?? null) : null;
}

// A failed hard rule against a warning, so a warning is never read as a failure.
export function reasonLabel(reason) {
  return reason.severity === "unsuitable" ? "Fails" : "Warning";
}
