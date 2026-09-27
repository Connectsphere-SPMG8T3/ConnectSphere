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
