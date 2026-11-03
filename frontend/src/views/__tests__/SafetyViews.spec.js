// CR-103 / CR-104: Safety Officer queue and operational decisions.
import { createPinia, setActivePinia } from 'pinia';
import { createApp, nextTick } from 'vue';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, eventsApi } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
import { toastState } from '@/composables/useToast';
import { useSafetyDecisionStore } from '@/features/events/safetyDecisionStore';
vi.mock('@/services/api', async (original) => ({
  ...(await original()),
  eventsApi: { safetyQueue: vi.fn(), safetyHistory: vi.fn(), safetyReview: vi.fn(), safetyApprove: vi.fn(), safetyRequestChanges: vi.fn(), safetyReject: vi.fn() },
}));
const decision = { id: 'd1', decision: 'changes_requested', organiser_comment: 'Keep the aisle clear', private_note: 'Hall manager is tight on space', checklist: [], reason_code: null,
  affected_booking_ids: ['b1'], affected_equipment_request_ids: ['q1'], rejected_venue_ids: [],
  decided_by_name: 'Officer Lee', decided_at: '2026-10-08T02:00:00Z' };
function response(overrides = {}) {
  return { event: { id: 'e1', name: 'Community Fair', organiser_name: 'Priya', coordinator_name: 'Marcus',
    starts_at: '2026-11-12T02:00:00Z', ends_at: '2026-11-12T04:00:00Z', expected_attendance: 80,
    accessibility_needs: 'Step-free access', registration: { enabled: true, capacity: 90, opens_at: '2026-10-10T02:00:00Z', closes_at: '2026-11-10T02:00:00Z' } },
    venues: [{ booking_id: 'b1', venue_id: 'v1', venue_name: 'Town Hall', booking_status: 'approved', capacity: 100,
      layouts: ['theatre', 'classroom'], accessibility_features: ['ramp', 'lift'], attendance_to_capacity: 0.8, emergency_access: null, restrictions: null }],
    equipment_lines: [{ id: 'q1', equipment_name: 'Projector', quantity: 2, status: 'pending' }],
    exit_confirmation: null, decisions: [decision], ...overrides };
}
const apps = [];
async function mountView(kind = 'review') {
  const pinia = createPinia(); setActivePinia(pinia);
  const auth = useAuthStore(); auth.token = 'access'; auth.profile = { id: 'officer', role: 'safety_officer', full_name: 'Officer Lee' };
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/dashboard/safety', name: 'dashboard-safety', component: { template: '<div />' } },
    { path: '/safety/events/:id', name: 'safety-review', component: { template: '<div />' } },
  ] });
  await router.push(kind === 'queue' ? '/dashboard/safety' : '/safety/events/e1');
  let View;
  if (kind === 'queue') View = (await import('@/views/dashboards/SafetyDashboard.vue')).default;
  else {
    const modules = import.meta.glob('../events/SafetyReviewView.vue');
    expect(modules['../events/SafetyReviewView.vue'], 'Safety review page exists').toBeTypeOf('function');
    View = (await modules['../events/SafetyReviewView.vue']()).default;
  }
  const el = document.createElement('div'); document.body.appendChild(el);
  const app = createApp(View).use(pinia).use(router); app.mount(el); apps.push(app);
  await nextTick();
  return { el, router, store: useSafetyDecisionStore() };
}
const button = (label) => document.querySelector(`button[aria-label="${label}"]`);
async function type(selector, value) {
  const field = document.querySelector(selector); field.value = value; field.dispatchEvent(new Event('input')); await nextTick();
}
// CR-108: the organiser's comment and the private notes are separate fields.
const comment = (value) => type('#safety-organiser-comment', value);
const privateNote = (value) => type('#safety-private-note', value);
// Mark every checklist factor with one rating (the venue radios named rejected-venue are not part of it).
async function markAll(rating = 'satisfactory') {
  for (const radio of document.querySelectorAll('input[type=radio][name^="bauhaus-radios-"]')) if (radio.value === rating) radio.click();
  await nextTick();
}
const checklistRows = (rating = 'satisfactory') => [
  ...['attendance_capacity', 'layout', 'emergency_access', 'accessibility', 'venue_restrictions'].map((factor) => ({ factor, booking_id: 'b1', rating, note: null })),
  { factor: 'equipment_placement', booking_id: null, rating, note: null },
];
const rejectRadio = () => document.querySelector('input[name="rejected-venue"]');
describe('Safety queue and review', () => {
  beforeEach(() => {
    document.body.innerHTML = ''; localStorage.clear(); vi.resetAllMocks();
    eventsApi.safetyQueue.mockResolvedValue({ items: [] }); eventsApi.safetyReview.mockResolvedValue(response());
    eventsApi.safetyHistory.mockResolvedValue({ items: [] });
  });
  afterEach(() => { apps.splice(0).forEach((app) => app.unmount()); vi.useRealTimers(); });
  it('CR-100 shows recorded emergency access and restrictions on the safety review', async () => {
    const data = response();
    data.venues[0].emergency_access = 'East exit\nCourtyard';
    data.venues[0].restrictions = 'No flames';
    eventsApi.safetyReview.mockResolvedValue(data);
    const { el } = await mountView();
    await vi.waitFor(() => expect(el.textContent).toContain('East exit\nCourtyard'));
    expect(el.textContent).toContain('No flames');
  });
  it('shows queue rows in server order and links to each review', async () => {
    eventsApi.safetyQueue.mockResolvedValue({ items: [
      { event_id: 'e1', name: 'Oldest Fair', organiser_name: 'Priya', starts_at: '2026-11-12T02:00:00Z', expected_attendance: 80, entered_review_at: '2026-10-08T02:00:00Z' },
      { event_id: 'e2', name: 'New Fair', organiser_name: 'Sam', starts_at: '2026-11-13T02:00:00Z', expected_attendance: 25, entered_review_at: '2026-10-09T02:00:00Z' },
    ] });
    const { el } = await mountView('queue');
    await vi.waitFor(() => expect(el.textContent).toContain('Oldest Fair'));
    expect(el.textContent.indexOf('Oldest Fair')).toBeLessThan(el.textContent.indexOf('New Fair'));
    expect(el.querySelector('a').getAttribute('href')).toBe('/safety/events/e1');
    for (const text of ['Priya', 'Sam', '80', '25', 'Waiting since', '8 Oct', '12 Nov']) expect(el.textContent).toContain(text);
  });
  it('shows the empty queue honestly', async () => {
    const { el } = await mountView('queue');
    await vi.waitFor(() => expect(el.textContent).toContain('No events are waiting for a safety check.'));
  });
  it('shows loading until the queue is available', async () => {
    let resolve; eventsApi.safetyQueue.mockImplementation(() => new Promise((r) => { resolve = r; }));
    const { el } = await mountView('queue'); expect(el.textContent).toContain('Loading');
    resolve({ items: [] }); await nextTick();
  });
  it('shows queue errors rather than an empty result', async () => {
    eventsApi.safetyQueue.mockRejectedValue(new Error('Queue unavailable'));
    const { el } = await mountView('queue');
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toBe('Queue unavailable'));
    expect(el.textContent).not.toContain('No events are waiting');
  });
  it('renders every review field and earlier decisions', async () => {
    const { el } = await mountView(); await vi.waitFor(() => expect(el.textContent).toContain('Community Fair'));
    for (const text of ['Priya', 'Marcus', '80', 'Step-free access', 'Town Hall', '100', 'theatre', 'classroom', 'ramp', 'lift', '80%', 'Projector', '2', 'pending', '90', '10 Oct', '10 Nov', 'Officer Lee', 'Keep the aisle clear', 'Hall manager is tight on space', 'Comment for the organiser', 'Private notes', 'Emergency access', 'Restrictions', 'Exit confirmation']) expect(el.textContent).toContain(text);
    expect(el.textContent.match(/Not recorded/g)).toHaveLength(3);
  });
  it('shows who ticked the exit check and when (SCRUM-24 AC10)', async () => {
    eventsApi.safetyReview.mockResolvedValue(response({ exit_confirmation: { confirmed_by_name: 'Tan Wei', confirmed_at: '2026-10-19T03:00:00Z' } }));
    const { el } = await mountView(); await vi.waitFor(() => expect(el.textContent).toContain('Community Fair'));
    expect(el.textContent).toContain('Exit confirmation');
    expect(el.textContent).toContain('Equipment does not block exits or walkways.');
    expect(el.textContent).toContain('Confirmed by Tan Wei');
  });
  it('renders absent equipment and no previous decisions', async () => {
    eventsApi.safetyReview.mockResolvedValue(response({ equipment_lines: [], decisions: [] }));
    const { el } = await mountView(); await vi.waitFor(() => expect(el.textContent).toContain('No equipment requested'));
    expect(el.textContent).toContain('No earlier safety decisions');
  });
  it('shows review loading and errors', async () => {
    let reject; eventsApi.safetyReview.mockImplementation(() => new Promise((_, r) => { reject = r; }));
    const { el } = await mountView(); expect(el.textContent).toContain('Loading');
    reject(new Error('Review unavailable'));
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toBe('Review unavailable'));
    expect(el.querySelector('textarea')).toBeNull();
    expect(el.querySelector('input[type=radio]')).toBeNull();
  });
  it('shows the six-factor checklist for each venue and for the whole event (AC1, AC2)', async () => {
    const { el } = await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull());
    const legends = [...el.querySelectorAll('legend')].map((legend) => legend.textContent.replace('*', '').trim());
    for (const factor of ['Attendance/capacity', 'Layout', 'Emergency access', 'Accessibility', 'Equipment placement', 'Venue restrictions']) expect(legends).toContain(factor);
    expect(el.textContent).toContain('Whole event');
    expect(el.textContent).toContain('Not applicable');
  });
  it('asks the five venue factors again for a second venue (AC2)', async () => {
    const second = { ...response().venues[0], booking_id: 'b2', venue_id: 'v2', venue_name: 'Atrium' };
    eventsApi.safetyReview.mockResolvedValue(response({ venues: [response().venues[0], second] }));
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    expect(document.querySelector('input[aria-label="Layout note for Atrium"]')).not.toBeNull();
    await markAll();
    expect(document.querySelectorAll('input[type=radio][name^="bauhaus-radios-"]:checked')).toHaveLength(11);
    expect(button('Approve').disabled).toBe(false);
  });
  it('blocks every decision until every factor is marked (AC3)', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    await comment('Move chairs'); rejectRadio().click(); await nextTick();
    for (const label of ['Approve', 'Request changes', 'Reject']) expect(button(label).disabled, label).toBe(true);
    expect(document.body.textContent).toContain('6 checklist marks still to make.');
    document.querySelector('input[type=radio][name^="bauhaus-radios-"][value="satisfactory"]').click(); await nextTick();
    expect(document.body.textContent).toContain('5 checklist marks still to make.');
    await markAll();
    for (const label of ['Approve', 'Request changes', 'Reject']) expect(button(label).disabled, label).toBe(false);
    expect(document.body.textContent).not.toContain('still to make');
  });
  it('says "1 checklist mark" when one mark is left', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    const radios = [...document.querySelectorAll('input[type=radio][name^="bauhaus-radios-"][value="satisfactory"]')];
    for (const radio of radios.slice(1)) radio.click(); await nextTick();
    expect(document.body.textContent).toContain('1 checklist mark still to make.');
    expect(document.body.textContent).not.toContain('1 checklist marks');
    expect(button('Approve').disabled).toBe(true);
  });
  it('requires an organiser comment to request changes or reject, but not to approve (AC4)', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull()); await markAll();
    expect(button('Approve').disabled).toBe(false); expect(button('Request changes').disabled).toBe(true); expect(button('Reject').disabled).toBe(true);
    await comment('   '); expect(button('Request changes').disabled).toBe(true);
    await comment('Move chairs'); expect(button('Request changes').disabled).toBe(false); expect(button('Reject').disabled).toBe(true);
    rejectRadio().click(); await nextTick();
    expect(button('Reject').disabled).toBe(false);
    expect(document.querySelector('#safety-organiser-comment').maxLength).toBe(1000);
    expect(document.querySelector('#safety-private-note').maxLength).toBe(1000);
  });
  it('does not need private notes for any decision', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull()); await markAll(); await comment('Move chairs');
    expect(document.querySelector('#safety-private-note').value).toBe('');
    expect(button('Request changes').disabled).toBe(false);
  });
  it('tells the officer which text the organiser sees and which stays private (AC4, AC5)', async () => {
    const { el } = await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull());
    expect(el.querySelector('label[for="safety-organiser-comment"]').textContent).toBe('Comment for the organiser');
    expect(el.querySelector('label[for="safety-private-note"]').textContent).toBe('Private notes (optional)');
    expect(el.querySelector('#safety-organiser-comment-hint').textContent).toContain('The organiser sees this with the outcome');
    expect(el.querySelector('#safety-private-note-hint').textContent).toContain('the organiser never does');
  });
  it('blocks approval while a factor is a Concern and says why, but still allows the other outcomes', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    await markAll(); await comment('Move chairs'); rejectRadio().click(); await nextTick();
    document.querySelector('input[type=radio][name^="bauhaus-radios-"][value="concern"]').click(); await nextTick();
    expect(button('Approve').disabled).toBe(true);
    expect(document.body.textContent).toContain("Approval isn't available while a factor is marked Concern.");
    expect(button('Request changes').disabled).toBe(false); expect(button('Reject').disabled).toBe(false);
  });
  it.each([
    ['Approve', 'Approve this event?', 'approve', 'safetyApprove', 'Event approved'],
    ['Request changes', 'Request changes?', 'requestChanges', 'safetyRequestChanges', 'Changes requested'],
    ['Reject', 'Reject this venue for the event?', 'reject', 'safetyReject', 'Venue rejected'],
  ])('confirms %s and sends only the selected arrangements before returning to queue', async (label, title, kind, api, toast) => {
    const { router } = await mountView(); await vi.waitFor(() => expect(button(label)).not.toBeNull());
    await markAll();
    if (kind !== 'approve') await comment('  Move the chairs  ');
    await privateNote('  Hall manager is tight on space  ');
    for (const box of document.querySelectorAll('input[type="checkbox"]')) { box.click(); } await nextTick();
    if (kind === 'reject') { rejectRadio().click(); await nextTick(); }
    button(label).click(); await nextTick();
    const dialog = document.querySelector('[role="dialog"]'); expect(dialog.textContent).toContain(title);
    if (kind === 'reject') expect(dialog.textContent).toContain("The event returns to Planning and this venue's booking is flagged Safety rejected. It is not released, and the event itself is not rejected.");
    if (kind === 'requestChanges') expect(dialog.textContent).toContain('The event returns to Planning. No booking or equipment changes status; the coordinator decides what to change.');
    eventsApi[api].mockResolvedValue({ id: 'e1', status: kind === 'approve' ? 'confirmed' : 'planning' });
    const confirm = dialog.querySelector(`button[aria-label="${label}"]`); expect(confirm).not.toBeNull(); confirm.click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('dashboard-safety'));
    const text = { checklist: checklistRows(), private_note: 'Hall manager is tight on space' };
    expect(eventsApi[api]).toHaveBeenCalledWith('e1', kind === 'approve' ? { ...text, organiser_comment: null } : kind === 'reject' ? { ...text, organiser_comment: 'Move the chairs', booking_id: 'b1' } : {
      ...text, organiser_comment: 'Move the chairs', booking_ids: ['b1'], equipment_request_ids: ['q1'],
    }, 'access');
    expect(toastState.value.message).toBe(toast);
  });
  it('disables rejection of a held venue and labels the separate selections', async () => {
    eventsApi.safetyReview.mockResolvedValue(response({ venues: [{...response().venues[0], booking_status:'held'}] }));
    const { el } = await mountView();
    await vi.waitFor(() => expect(rejectRadio()).not.toBeNull());
    expect(rejectRadio().disabled).toBe(true);
    const legends = [...el.querySelectorAll('legend')].map((legend) => legend.textContent.trim());
    expect(legends).toContain('For Request changes: what needs changing (optional)');
    expect(legends).toContain('For Reject: venue that fails the safety check (required)');
    expect(el.textContent).toContain('Tick the venues and equipment your comment is about, so the coordinator knows what to revise.');
    expect(el.textContent).toContain('Choose one venue. Only approved bookings can be rejected; the event goes back to Planning.');
    for (const fieldset of el.querySelectorAll('fieldset[aria-describedby]')) {
      expect(el.querySelector(`#${fieldset.getAttribute('aria-describedby')}`)).not.toBeNull();
    }
  });
  it('cancels confirmation without sending a decision', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await markAll(); button('Approve').click(); await nextTick();
    button('Cancel').click(); await nextTick(); expect(document.querySelector('[role="dialog"]')).toBeNull(); expect(eventsApi.safetyApprove).not.toHaveBeenCalled();
  });
  it.each([409, 422])('shows a %s refusal in the page without navigating', async (status) => {
    const { el, router } = await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await markAll();
    eventsApi.safetyApprove.mockRejectedValue(new ApiError('Arrangements changed: reload', status));
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toBe('Arrangements changed: reload'));
    expect(router.currentRoute.value.name).toBe('safety-review');
  });
  it('does not submit twice while a decision is pending', async () => {
    let resolve; eventsApi.safetyApprove.mockImplementation(() => new Promise((r) => { resolve = r; }));
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await markAll();
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click(); await nextTick();
    expect(button('Approve').disabled).toBe(true); expect(eventsApi.safetyApprove).toHaveBeenCalledTimes(1);
    resolve({ id: 'e1', status: 'confirmed' }); await vi.waitFor(() => expect(toastState.value.message).toBe('Event approved'));
  });
  it('refuses to confirm a review belonging to a different event', async () => {
    const { el, store, router } = await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await markAll();
    button('Approve').click(); await nextTick();
    store.review = response({ event: { ...response().event, id: 'another-event' } });
    eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent).toContain('Reload the event before deciding'));
    expect(eventsApi.safetyApprove).not.toHaveBeenCalled(); expect(router.currentRoute.value.name).toBe('safety-review');
  });
  it.each(['', '   ', '  Crowd flow checked  '])('submits the trimmed optional approval comment %j', async (text) => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await markAll(); await comment(text);
    eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(eventsApi.safetyApprove).toHaveBeenCalledWith('e1', { checklist: checklistRows(), organiser_comment: text.trim() || null, private_note: null }, 'access'));
  });
  it('sends a note on a factor and sends a blank private note as none (AC1, AC4)', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull()); await markAll('concern');
    await type('input[aria-label="Layout note for Town Hall"]', '  Aisle too narrow  ');
    await comment('Widen the aisle'); await privateNote('   ');
    eventsApi.safetyRequestChanges.mockResolvedValue({ id: 'e1', status: 'planning' });
    button('Request changes').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Request changes"]').click();
    await vi.waitFor(() => expect(eventsApi.safetyRequestChanges).toHaveBeenCalled());
    const [, payload] = eventsApi.safetyRequestChanges.mock.calls[0];
    expect(payload.private_note).toBeNull();
    expect(payload.checklist.find((row) => row.factor === 'layout')).toEqual({ factor: 'layout', booking_id: 'b1', rating: 'concern', note: 'Aisle too narrow' });
    expect(payload.checklist).toHaveLength(6);
  });

});

const flushPromises = () => new Promise((resolve) => setTimeout(resolve));
describe('Safety Officer dashboard overview (CR-103 AC7)', () => {
  const tile = (label) => [...document.querySelectorAll('p')].find((p) => p.textContent.trim() === label)?.parentElement;
  beforeEach(() => {
    document.body.innerHTML = ''; localStorage.clear(); vi.resetAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-09T12:00:00Z'));
    eventsApi.safetyQueue.mockResolvedValue({ items: [
      { event_id: 'e1', name: 'Oldest Fair', organiser_name: 'Priya', starts_at: null, expected_attendance: 80, entered_review_at: '2026-10-07T11:00:00Z' },
      { event_id: 'e2', name: 'New Fair', organiser_name: 'Sam', starts_at: null, expected_attendance: 25, entered_review_at: '2026-10-09T09:00:00Z' },
    ] });
    eventsApi.safetyHistory.mockResolvedValue({ items: [
      { id: 'h3', event_id: 'e7', event_name: 'Gala Night', decision: 'withdrawn', organiser_comment: null, private_note: null, decided_by_name: null, decided_at: '2026-10-09T03:00:00Z' },
      { id: 'h2', event_id: 'e6', event_name: 'Book Fair', decision: 'arrangement_rejected', organiser_comment: 'Venue too small', private_note: 'Fire marshal unhappy', decided_by_name: 'Hafiz Ismail', decided_at: '2026-10-08T03:00:00Z' },
      { id: 'h1', event_id: 'e5', event_name: 'Year-End Dinner', decision: 'approved', organiser_comment: null, private_note: null, decided_by_name: 'Hafiz Ismail', decided_at: '2026-10-05T03:00:00Z' },
    ] });
  });
  afterEach(() => { apps.splice(0).forEach((app) => app.unmount()); vi.useRealTimers(); });

  it('shows the queue figures counted from the loaded queue', async () => {
    await mountView('queue'); await flushPromises();
    expect(tile('In queue').textContent).toContain('2');
    expect(tile('Oldest waiting').textContent).toContain('2 days');
  });

  it('counts the last 30 days of decisions by outcome, leaving withdrawals out', async () => {
    await mountView('queue'); await flushPromises();
    expect(tile('Approved').textContent).toMatch(/1\s*Last 30 days/);
    expect(tile('Changes requested').textContent).toMatch(/0\s*Last 30 days/);
    expect(tile('Arrangement rejected').textContent).toMatch(/1\s*Last 30 days/);
  });

  it('lists recent decisions newest first with event, outcome, decider and comment', async () => {
    const { el } = await mountView('queue'); await flushPromises();
    const rows = [...el.querySelectorAll('[data-history-item]')].map((row) => row.textContent);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toContain('Gala Night'); expect(rows[0]).toContain('Withdrawn'); expect(rows[0]).toContain('System');
    expect(rows[1]).toContain('Book Fair'); expect(rows[1]).toContain('Arrangement rejected');
    expect(rows[1]).toContain('Hafiz Ismail'); expect(rows[1]).toContain('Venue too small'); expect(rows[1]).toContain('Fire marshal unhappy');
    expect(rows[2]).toContain('Year-End Dinner');
  });

  it('shows empty figures and an empty history state', async () => {
    eventsApi.safetyQueue.mockResolvedValue({ items: [] }); eventsApi.safetyHistory.mockResolvedValue({ items: [] });
    const { el } = await mountView('queue'); await flushPromises();
    expect(tile('In queue').textContent).toContain('0'); expect(tile('Oldest waiting').textContent).toContain('—');
    expect(el.textContent).toContain('No safety decisions in the last 30 days.');
  });

  it('keeps the queue when the history fails to load', async () => {
    eventsApi.safetyHistory.mockRejectedValue(new Error('History unavailable'));
    const { el } = await mountView('queue'); await flushPromises();
    expect(el.textContent).toContain('History unavailable');
    expect(el.textContent).toContain('Oldest Fair');
  });
});
