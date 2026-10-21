// SCRUM-82: mirrored lists keep safety review visible.
import {expect, it} from "vitest";
import {ACTIVE_COORDINATOR_STATUSES, readinessGaps} from "../dashboard";
import {COMMENTABLE_STATUSES} from "../comments";
import {groupOrganiserActiveEvents} from "../organiserDashboard";
it("includes safety review in dashboards and comments", () => {
 expect(ACTIVE_COORDINATOR_STATUSES).toContain("safety_review"); expect(COMMENTABLE_STATUSES).toContain("safety_review");
 const events=[{id:"e",status:"safety_review"}];
 expect(groupOrganiserActiveEvents(events).find(g=>g.status==="safety_review").events).toEqual(events);
});

it("SCRUM-82 flags safety-review readiness gaps", () => {
 const events=[{event_id:"e",status:"safety_review",starts_at:"2026-11-02T00:00:00Z",readiness:{venue:"pending",equipment:"not_required",technical:"ready"}}];
 expect(readinessGaps(events,{now:new Date("2026-11-01T00:00:00Z")})).toEqual(events);
});
