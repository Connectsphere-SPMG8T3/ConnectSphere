// CR-110 technical preparation (REQUIREMENTS RD-R2). The API decides when it
// can be recorded and moves the event to Preparation; these only label the
// stages and choose when to offer the form.

// The stages named in the M3 meeting, shared with venue preparation (CR-109).
export const PREPARATION_STAGE_LABELS = {
  not_started: "Not started",
  in_preparation: "In preparation",
  in_progress: "In progress",
  completed: "Completed",
};

export const PREPARATION_STAGE_OPTIONS = Object.entries(PREPARATION_STAGE_LABELS)
  .map(([value, label]) => ({ value, label }));

// AC1: the API's refusal, shown before anyone tries.
export const PREPARATION_LOCKED_MESSAGE = "Technical preparation opens once the Safety Officer has confirmed the event.";

const OPEN_STATUSES = new Set(["confirmed", "preparation"]);

export function isOpenForPreparation(eventStatus) {
  return OPEN_STATUSES.has(eventStatus);
}

export function preparationStageLabel(stage) {
  return PREPARATION_STAGE_LABELS[stage ?? "not_started"] ?? stage;
}
