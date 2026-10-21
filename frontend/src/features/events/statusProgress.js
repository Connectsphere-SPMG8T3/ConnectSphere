import { STATUS_LABELS } from "@/features/events/dashboard";

/**
 * The coordinator's part of the event lifecycle, in order (REQUIREMENTS §5).
 * An event reaches a coordinator at `under_review`, so `draft` and `submitted`
 * aren't steps here. `preparation` (QA3-3) joins between `confirmed` and
 * `completed` once that status exists.
 */
export const COORDINATOR_PROGRESS_STEPS = ["under_review", "planning", "safety_review", "confirmed", "completed"];

/**
 * Where an event sits on the progress bar. `kind` is "on-track" on the main
 * path; "returned" when the request is back with the organiser, which holds it
 * at Under review; and "ended" for rejected, cancelled or unknown statuses,
 * which have no position on the bar because the status alone doesn't say
 * which step it stopped at.
 */
export function statusProgress(status, steps = COORDINATOR_PROGRESS_STEPS) {
  if (status === "returned") {
    return {
      kind: "returned",
      steps: steps.map((step, index) => ({
        status: step,
        label: index === 0 ? STATUS_LABELS.returned : STATUS_LABELS[step],
        state: index === 0 ? "returned" : "upcoming",
      })),
    };
  }
  const position = steps.indexOf(status);
  if (position === -1) {
    return { kind: "ended", steps: [], label: STATUS_LABELS[status] ?? status };
  }
  const finished = position === steps.length - 1;
  return {
    kind: "on-track",
    steps: steps.map((step, index) => ({
      status: step,
      label: STATUS_LABELS[step],
      state: index < position || finished ? "done" : index === position ? "current" : "upcoming",
    })),
  };
}
