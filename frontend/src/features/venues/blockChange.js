import { expiryInputToIso } from "@/features/venues/dashboard";
import { formatVenueInstant } from "@/features/venues/venueProfile";

/**
 * SCRUM-54 AC2: ending a block now, shortening it, or removing one that hasn't
 * started, as pure functions. The API enforces the same rules under the venue
 * lock; these decide which buttons a block offers and let the dialog name each
 * problem before anything is sent. Times are datetime-local picks read as
 * Singapore time.
 */

export const BLOCK_CHANGE_NOTE_MAX_LENGTH = 1000;

export const BLOCK_CHANGE_ACTIONS = {
  end_now: "End now",
  shorten: "Shorten",
  remove: "Remove",
};

const BLOCK_STATUS_LABELS = {
  active: "Active",
  ended_early: "Ended early",
  removed: "Removed",
};

export function blockStatusLabel(status) {
  return BLOCK_STATUS_LABELS[status] ?? BLOCK_STATUS_LABELS.active;
}

/**
 * The changes a block allows at `now`: a started one can be ended now or
 * shortened, one that hasn't started shortened or removed. One that has ended
 * or was removed allows none (AC2).
 */
export function blockActions(block, now = new Date()) {
  if (!block?.period || block.status === "removed") return [];
  const starts = new Date(block.period.starts_at);
  const ends = new Date(block.period.ends_at);
  if (ends <= now) return [];
  return starts <= now ? ["end_now", "shorten"] : ["shorten", "remove"];
}

export function emptyBlockChange(action = "") {
  return { action, endsAt: "", note: "" };
}

/** `{field: message}` for every problem with the change; empty when it can be sent. */
export function validateBlockChange(form, block, now = new Date()) {
  const errors = {};
  if (!form.action) errors.action = "Choose what to do.";
  if (form.action === "shorten") {
    const ends = expiryInputToIso(form.endsAt);
    if (!ends) {
      errors.endsAt = "Choose the new end.";
    } else if (new Date(ends) <= now) {
      errors.endsAt = "The new end must be in the future. To end the block now, choose End now.";
    } else if (new Date(ends) <= new Date(block.period.starts_at)) {
      errors.endsAt = "The new end must be after the block's start.";
    } else if (new Date(ends) >= new Date(block.period.ends_at)) {
      errors.endsAt = "The new end must be earlier than the current end. To block for longer, add a new block.";
    }
  }
  if ((form.note ?? "").trim().length > BLOCK_CHANGE_NOTE_MAX_LENGTH) {
    errors.note = `The note can be at most ${BLOCK_CHANGE_NOTE_MAX_LENGTH} characters.`;
  }
  return errors;
}

/** The `POST /venues/{id}/blocks/{block_id}/change` body for a valid form. */
export function toBlockChangePayload(form) {
  return {
    action: form.action,
    ends_at: form.action === "shorten" ? expiryInputToIso(form.endsAt) : null,
    note: (form.note ?? "").trim() || null,
  };
}

/** AC1: who set the block and when, or "Unknown user" when that wasn't recorded. */
export function blockSetBy(block) {
  const who = `Set by ${block?.created_by?.full_name ?? "Unknown user"}`;
  return block?.created_at ? `${who} · ${formatVenueInstant(block.created_at)}` : who;
}
