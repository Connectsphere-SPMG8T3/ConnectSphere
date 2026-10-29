// Story 32: the organiser's change request. The API is the enforcement point and
// diffs the proposal again against the database; this only builds the proposal
// and avoids offering a request the API would refuse.
import { fieldLabel } from "@/features/events/amendment";

// CR-R15: accepted from submission until the event starts, except on a returned
// request, which is amended and resubmitted directly.
const REQUESTABLE_STATUSES = new Set(["submitted", "under_review", "planning", "safety_review", "confirmed", "preparation"]);

export function canRequestChange(event, now = new Date()) {
  if (!event || !REQUESTABLE_STATUSES.has(event.status)) return false;
  // CR-R14: one open request per event.
  if (event.open_change_request || event.open_cancellation_request) return false;
  return !event.starts_at || new Date(event.starts_at) > now;
}

const TIME_FIELDS = new Set([
  "starts_at", "ends_at", "registration_opens_at", "registration_closes_at",
]);

// Q10, mirroring the API: blank text is no text, lists are sets, times are instants.
function comparable(field, value) {
  if (typeof value === "string") value = value.trim() || null;
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) return JSON.stringify([...value].sort());
  if (TIME_FIELDS.has(field)) return new Date(value).getTime();
  return value;
}

function changedFields(before, after) {
  return Object.fromEntries(
    Object.entries(after).filter(([field, value]) => comparable(field, before?.[field]) !== comparable(field, value)),
  );
}

// `before` and `after` are payload snapshots, `{event, spaces: [{id, ...}]}`, built
// the same way the form saves, so timezones convert identically on both sides.
export function diffProposal(before, after) {
  const spacesBefore = new Map(before.spaces.map((space) => [space.id, space]));
  const spaces = after.spaces
    .map(({ id, ...values }) => ({ id, ...changedFields(spacesBefore.get(id), values) }))
    .filter((space) => Object.keys(space).length > 1);
  return { event: changedFields(before.event, after.event), spaces };
}

export function hasChanges(proposal) {
  return Object.keys(proposal.event).length > 0 || proposal.spaces.length > 0;
}

const SPACE_FIELD_LABELS = {
  label: "space name",
  expected_pax: "attendance",
  layout_preference: "layout",
  facilities_required: "facilities",
  starts_at: "start time",
  ends_at: "end time",
};

function shown(value) {
  if (value === null || value === undefined || value === "") return "(none)";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "(none)";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

// A request's stored changes as display rows: `{key, label, before, after}`.
export function describeChanges(changes) {
  if (!changes) return [];
  const rows = changes.event.map(({ field, before, after }) => ({
    key: `event:${field}`,
    label: fieldLabel(field),
    before: shown(before),
    after: shown(after),
  }));
  for (const space of changes.spaces) {
    for (const { field, before, after } of space.fields) {
      rows.push({
        key: `${space.space_id}:${field}`,
        label: `${space.label}: ${SPACE_FIELD_LABELS[field] ?? field}`,
        before: shown(before),
        after: shown(after),
      });
    }
  }
  return rows;
}
