// CR-108 (QA3-17): the Safety Officer's six-factor checklist. Five factors are marked for every venue
// booking; equipment placement is marked once for the event. Marks are kept in an object keyed by
// `markKey`, each `{ rating, note }`, so the form can bind to them directly.

export const SAFETY_FACTORS = [
  { value: "attendance_capacity", label: "Attendance/capacity", scope: "venue" },
  { value: "layout", label: "Layout", scope: "venue" },
  { value: "emergency_access", label: "Emergency access", scope: "venue" },
  { value: "accessibility", label: "Accessibility", scope: "venue" },
  { value: "equipment_placement", label: "Equipment placement", scope: "event" },
  { value: "venue_restrictions", label: "Venue restrictions", scope: "venue" },
];

export const SAFETY_RATINGS = [
  { value: "satisfactory", label: "Satisfactory" },
  { value: "concern", label: "Concern" },
  { value: "not_applicable", label: "Not applicable" },
];

export const VENUE_FACTORS = SAFETY_FACTORS.filter((f) => f.scope === "venue").map((f) => f.value);
const EQUIPMENT_FACTOR = "equipment_placement";

export const factorLabel = (value) => SAFETY_FACTORS.find((f) => f.value === value)?.label ?? value;
export const ratingLabel = (value) => SAFETY_RATINGS.find((r) => r.value === value)?.label ?? value;

export const markKey = (factor, bookingId) => `${factor}:${bookingId ?? "event"}`;

// Every mark the checklist asks for, in the order the form shows them.
function expectedMarks(bookingIds) {
  return [
    ...bookingIds.flatMap((bookingId) => VENUE_FACTORS.map((factor) => ({ factor, bookingId }))),
    { factor: EQUIPMENT_FACTOR, bookingId: null },
  ];
}

// AC3: the marks still to make. A note alone is not a mark.
export function missingMarks(marks, bookingIds) {
  return expectedMarks(bookingIds).filter(({ factor, bookingId }) => !marks[markKey(factor, bookingId)]?.rating);
}

// Marks for a venue that has since left the review are ignored.
export function hasConcern(marks, bookingIds) {
  const inScope = bookingIds ? new Set(expectedMarks(bookingIds).map((m) => markKey(m.factor, m.bookingId))) : null;
  return Object.entries(marks).some(([key, mark]) => mark.rating === "concern" && (!inScope || inScope.has(key)));
}

// Team decision (CR-108): a factor marked Concern blocks approval; request changes or reject instead.
export const canApprove = (marks, bookingIds) =>
  missingMarks(marks, bookingIds).length === 0 && !hasConcern(marks, bookingIds);

// The rows the API takes. An unmarked factor is left out for the server to refuse, never guessed.
export function buildChecklist(marks, bookingIds) {
  return expectedMarks(bookingIds).flatMap(({ factor, bookingId }) => {
    const mark = marks[markKey(factor, bookingId)];
    if (!mark?.rating) return [];
    return [{ factor, booking_id: bookingId, rating: mark.rating, note: mark.note?.trim() || null }];
  });
}
