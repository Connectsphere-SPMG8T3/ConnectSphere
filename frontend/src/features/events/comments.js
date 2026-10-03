// SCRUM-61 comment rules. The API is the enforcement point (events/service.py,
// public.add_event_comment); these only avoid offering a post that would fail.

// Mirrors the API's COMMENT_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const COMMENT_MAX_LENGTH = 1000;

export const COMMENTABLE_STATUSES = ["submitted", "under_review", "returned", "planning", "confirmed"];

export function canPost(status) {
  return COMMENTABLE_STATUSES.includes(status);
}

export function hasThread(status) {
  return Boolean(status) && status !== "draft";
}

export function validateComment(text) {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return "A comment can't be empty.";
  if (trimmed.length > COMMENT_MAX_LENGTH) return `Keep it to ${COMMENT_MAX_LENGTH} characters.`;
  return null;
}
