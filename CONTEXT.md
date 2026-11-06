# ConnectSphere

Event planning and venue booking for one organisation. Event Organisers request events; Event Coordinators review them and arrange venues and equipment; Venue Staff and Tech Support decide on those arrangements. Business rules come from `docs/REQUIREMENTS.md`; this file is only the shared vocabulary.

## Language

### Venues

**Venue**:
A single bookable space in the catalogue. It hosts one event at a time; there are no sub-rooms.
_Avoid_: Room, hall, space, location (location is a venue's address attribute)

**Active venue**:
A venue that can appear in search and be booked. Inactive venues are hidden from search but stay on historic bookings.
_Avoid_: Enabled, live, deleted

**Block**:
A period during which Venue Staff have made a venue unbookable, with a reason (maintenance, renovation, safety, internal activity, other). Any block, whatever its reason, makes the venue unavailable for new holds.
_Avoid_: Unavailability, downtime, closure, maintenance window

**Hold**:
A tentative claim on a venue for an event's period, created the moment a booking request is submitted and lasting until Venue Staff decide on it. A hold occupies the venue exactly like an approved booking.
_Avoid_: Reservation, pending booking, soft booking

**Booking**:
The record of an event's claim on a venue, in one of the statuses held, approved, re-review, rejected, cancelled, released. Only held, approved and re-review bookings occupy the venue.
_Avoid_: Reservation, allocation

**Occupied period**:
The half-open interval `[starts_at, ends_at)` during which a booking or block occupies a venue. Two periods conflict only if they overlap; a period ending at 12:00 and one starting at 12:00 do not.
_Avoid_: Slot, time slot, window

**Turnaround**:
Time between consecutive bookings for setup or reset. The customer has set it to zero (QA-28), so it never affects availability. The term exists only so the decision is nameable.
_Avoid_: Buffer, setup time, reset time, changeover

### Finding a venue

**Availability**:
Whether a venue is free of any occupying booking or block during a given occupied period. Answers "right room, wrong time?".
_Avoid_: Free, open, vacancy

**Suitability**:
Whether a venue's attributes (capacity, facilities, layouts, accessibility, operating hours) meet an event's requirements. Answers "wrong room?". Independent of availability.
_Avoid_: Fit, match, eligibility, compatibility

**Search criteria**:
The set of requirements a coordinator searches venues against: occupied period, minimum capacity, location, layout, required facilities, accessibility features. Every criterion the coordinator sets is strict — a venue that misses it is excluded, with the reason recorded.
_Avoid_: Filters, query, preferences

**Excluded venue**:
A venue left out of default search results because it is inactive, fails a search criterion, or is unavailable. Each exclusion carries a reason and can be revealed on request.
_Avoid_: Hidden, filtered out, unsuitable (suitability is only one cause of exclusion)

### Accounts

**Sign-up**:
An external person creating their own ConnectSphere account as either an Event Organiser or an Attendee. Internal staff never sign up; their accounts are system defaults.
_Avoid_: Registration, register, account creation, onboarding

**Registration**:
An attendee's place on a specific event, in one of the statuses registered, waitlisted, invited, withdrawn or cancelled. Never used for creating an account.
_Avoid_: Sign-up, booking, RSVP, enrolment

### Event lifecycle

**Cancellation request**:
An organiser's open request, with a reason, to cancel their own event. It releases nothing until the assigned coordinator decides it.
_Avoid_: Cancel request, withdrawal

**Direct cancellation**:
The assigned coordinator cancelling an event without an organiser request. It is allowed only in Confirmed or Preparation, only before the event's start time, and not while a cancellation request is open.
_Avoid_: Coordinator cancel, forced cancel

**Cancelled**:
The terminal status of an event that has been cancelled, either by an approved cancellation request or by direct cancellation. Its arrangements are released.
_Avoid_: Deleted, withdrawn

**Rejected**:
The terminal status of an event request a coordinator declined before it was confirmed. It is not the word for a cancellation request being declined; that is a **rejected cancellation request**.
_Avoid_: Cancelled (for a declined request)

**Release**:
Freeing an event's arrangements (venue bookings, equipment reservations, registrations) so their capacity is available again. Release happens on cancellation and rejection, never automatically on a change.
_Avoid_: Delete, unbook, drop

**Arrangements**:
The venue bookings, equipment reservations and registrations an event holds.

### Changes to an event

**Change request**:
An organiser's request, with a reason, to change details of their own event after submitting it. Nothing changes until the assigned coordinator approves it; it is approved or rejected as a whole.
_Avoid_: Edit request, amendment (an amendment is what an organiser does to a request returned to them)

**Significant change**:
A change to the date or time, the attendance, or the venue or equipment requirements. Approving one sends a confirmed event back through the safety check. Any other change is an **ordinary change**.
_Avoid_: Major change, material change

**Needs re-review**:
An arrangement an approved change touched in a way its staff had already approved, such as a booking whose time or layout changed. It keeps its hold or reservation and counts as not ready until the coordinator sends it for re-review. It is not a reset.
_Avoid_: Flagged, reset, unconfirmed

**Send for re-review**:
The coordinator handing an arrangement that needs re-review to venue staff or technical support, optionally with a note.
_Avoid_: Resubmit, re-request

**Under re-review**:
An arrangement with venue staff or technical support again after an approved change. It still holds the venue or equipment until they approve it again or reject it. It can happen any number of times.
_Avoid_: Pending, re-requested

### Readiness and preparation

**Technical status**:
Whether an event's equipment arrangements are ready for the safety check: Ready, Pending, Issue or Not required. Nobody sets it; it follows from the equipment lines and the exit check. It is not the same as **technical preparation**.
_Avoid_: Technical readiness (in conversation), technical progress

**Preparation**:
The event status after Confirmed, entered automatically when venue staff or technical support record the first preparation update on a Confirmed event. An event back in Planning and confirmed again enters it again on its next update.
_Avoid_: Prepping, in progress (as a status)

**Technical preparation**:
Technical support's own record of how far they are with setting up an event's technical arrangements once it is Confirmed, as one **preparation stage** for the whole event plus an internal note. It never changes the **technical status**. It can be updated only while the event is Confirmed or in Preparation; at any other status it is kept but locked.
_Avoid_: Technical status, technical readiness, tech sign-off

**Venue preparation**:
The same record kept by venue staff, one per venue booking.

**Preparation stage**:
One of Not started, In preparation, In progress or Completed. Stages can be set in any order, including back from Completed. The organiser sees the stage, never the note.
_Avoid_: Preparation status, progress status

### Change history

**Change history**:
The record of what changed on an event, who changed it and when, read together from every part of the event that keeps its own record. Its entries are never edited or removed.
_Avoid_: Audit log, activity log, change log

**History entry**:
One recorded change in an event's **change history**: a status change, an edit to a field with its old and new value, a decision, or a preparation update.
_Avoid_: Log line, audit record
