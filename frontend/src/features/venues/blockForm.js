import { BLOCK_REASON_LABELS, expiryInputToIso } from "@/features/venues/dashboard";

/**
 * SCRUM-51 AC1: the rules of the Block venue form, as pure functions. The API
 * enforces the same rules; these let the form name each problem before it is
 * sent. Times are datetime-local picks read as Singapore time.
 */

export const BLOCK_DETAIL_MAX_LENGTH = 1000;

/** The reason categories, in the order the story lists them. Mirrors `public.venue_block_reason`. */
export const BLOCK_REASONS = Object.entries(BLOCK_REASON_LABELS).map(([value, label]) => ({ value, label }));

export function emptyBlockForm() {
  return { startsAt: "", endsAt: "", reason: "", detail: "" };
}

/** `{field: message}` for every problem with the form; empty when it can be sent. */
export function validateBlockForm(form, now = new Date()) {
  const errors = {};
  const starts = expiryInputToIso(form.startsAt);
  const ends = expiryInputToIso(form.endsAt);
  if (!starts) errors.startsAt = "Choose a start date and time.";
  if (!ends) errors.endsAt = "Choose an end date and time.";
  else if (starts && new Date(ends) <= new Date(starts)) errors.endsAt = "End must be after start.";
  else if (new Date(ends) <= now) errors.endsAt = "End must be in the future.";
  if (!form.reason) errors.reason = "Choose a reason.";

  const detail = (form.detail ?? "").trim();
  if (detail.length > BLOCK_DETAIL_MAX_LENGTH) {
    errors.detail = `The detail can be at most ${BLOCK_DETAIL_MAX_LENGTH} characters.`;
  } else if (form.reason === "other" && !detail) {
    errors.detail = "A detail is required when the reason is Other.";
  }
  return errors;
}

/** The `POST /venues/{id}/blocks` body for a valid form. */
export function toBlockPayload(form, { confirm = false } = {}) {
  return {
    starts_at: expiryInputToIso(form.startsAt),
    ends_at: expiryInputToIso(form.endsAt),
    reason: form.reason,
    detail: (form.detail ?? "").trim() || null,
    confirm,
  };
}
