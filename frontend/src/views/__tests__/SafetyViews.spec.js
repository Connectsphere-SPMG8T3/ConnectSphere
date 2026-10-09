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
const decision = { id: 'd1', decision: 'changes_requested', comment: 'Keep the aisle clear', reason_code: null,
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
async function comment(value) {
  const field = document.querySelector('textarea'); field.value = value; field.dispatchEvent(new Event('input')); await nextTick();
}
describe('Safety queue and review', () => {
  beforeEach(() => {
    document.body.innerHTML = ''; localStorage.clear(); vi.resetAllMocks();
    eventsApi.safetyQueue.mockResolvedValue({ items: [] }); eventsApi.safetyReview.mockResolvedValue(response());
    eventsApi.safetyHistory.mockResolvedValue({ items: [] });
  });
  afterEach(() => { apps.splice(0).forEach((app) => app.unmount()); vi.useRealTimers(); });
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
    for (const text of ['Priya', 'Marcus', '80', 'Step-free access', 'Town Hall', '100', 'theatre', 'classroom', 'ramp', 'lift', '80%', 'Projector', '2', 'pending', '90', '10 Oct', '10 Nov', 'Officer Lee', 'Keep the aisle clear', 'Record any crowd-movement concerns here.', 'Emergency access', 'Restrictions', 'Exit confirmation']) expect(el.textContent).toContain(text);
    expect(el.textContent.match(/Not recorded/g)).toHaveLength(3);
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
  });
  it('requires a nonblank comment for returning decisions but not approval', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Request changes')).not.toBeNull());
    expect(button('Approve').disabled).toBe(false); expect(button('Request changes').disabled).toBe(true); expect(button('Reject').disabled).toBe(true);
    await comment('   '); expect(button('Request changes').disabled).toBe(true);
    await comment('Move chairs'); expect(button('Request changes').disabled).toBe(false); expect(button('Reject').disabled).toBe(false);
    expect(document.querySelector('textarea').maxLength).toBe(1000);
  });
  it.each([
    ['Approve', 'Approve this event?', 'approve', 'safetyApprove', 'Event approved'],
    ['Request changes', 'Request changes?', 'requestChanges', 'safetyRequestChanges', 'Changes requested'],
    ['Reject', 'Reject the safety arrangement?', 'reject', 'safetyReject', 'Arrangement rejected'],
  ])('confirms %s and sends only the selected arrangements before returning to queue', async (label, title, kind, api, toast) => {
    const { router } = await mountView(); await vi.waitFor(() => expect(button(label)).not.toBeNull());
    if (kind !== 'approve') await comment('  Move the chairs  ');
    for (const box of document.querySelectorAll('input[type="checkbox"]')) { box.click(); } await nextTick();
    button(label).click(); await nextTick();
    const dialog = document.querySelector('[role="dialog"]'); expect(dialog.textContent).toContain(title);
    if (kind === 'reject') { expect(dialog.textContent).toContain('must be replaced'); expect(dialog.textContent).toContain('event itself is not rejected'); }
    eventsApi[api].mockResolvedValue({ id: 'e1', status: kind === 'approve' ? 'confirmed' : 'planning' });
    const confirm = dialog.querySelector(`button[aria-label="${label}"]`); expect(confirm).not.toBeNull(); confirm.click();
    await vi.waitFor(() => expect(router.currentRoute.value.name).toBe('dashboard-safety'));
    expect(eventsApi[api]).toHaveBeenCalledWith('e1', kind === 'approve' ? { comment: null } : {
      [kind === 'reject' ? 'reason' : 'comment']: 'Move the chairs', booking_ids: ['b1'], equipment_request_ids: ['q1'],
    }, 'access');
    expect(toastState.value.message).toBe(toast);
  });
  it('cancels confirmation without sending a decision', async () => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); button('Approve').click(); await nextTick();
    button('Cancel').click(); await nextTick(); expect(document.querySelector('[role="dialog"]')).toBeNull(); expect(eventsApi.safetyApprove).not.toHaveBeenCalled();
  });
  it.each([409, 422])('shows a %s refusal in the page without navigating', async (status) => {
    const { el, router } = await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    eventsApi.safetyApprove.mockRejectedValue(new ApiError('Arrangements changed: reload', status));
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]').textContent).toBe('Arrangements changed: reload'));
    expect(router.currentRoute.value.name).toBe('safety-review');
  });
  it('does not submit twice while a decision is pending', async () => {
    let resolve; eventsApi.safetyApprove.mockImplementation(() => new Promise((r) => { resolve = r; }));
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click(); await nextTick();
    expect(button('Approve').disabled).toBe(true); expect(eventsApi.safetyApprove).toHaveBeenCalledTimes(1);
    resolve({ id: 'e1', status: 'confirmed' }); await vi.waitFor(() => expect(toastState.value.message).toBe('Event approved'));
  });
  it('refuses to confirm a review belonging to a different event', async () => {
    const { el, store, router } = await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull());
    button('Approve').click(); await nextTick();
    store.review = response({ event: { ...response().event, id: 'another-event' } });
    eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(el.querySelector('[role="alert"]')?.textContent).toContain('Reload the event before deciding'));
    expect(eventsApi.safetyApprove).not.toHaveBeenCalled(); expect(router.currentRoute.value.name).toBe('safety-review');
  });
  it.each(['', '   ', '  Crowd flow checked  '])('submits the trimmed optional approval comment %j', async (text) => {
    await mountView(); await vi.waitFor(() => expect(button('Approve')).not.toBeNull()); await comment(text);
    eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    button('Approve').click(); await nextTick(); document.querySelector('[role="dialog"] button[aria-label="Approve"]').click();
    await vi.waitFor(() => expect(eventsApi.safetyApprove).toHaveBeenCalledWith('e1', { comment: text.trim() || null }, 'access'));
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
      { id: 'h3', event_id: 'e7', event_name: 'Gala Night', decision: 'withdrawn', comment: null, decided_by_name: null, decided_at: '2026-10-09T03:00:00Z' },
      { id: 'h2', event_id: 'e6', event_name: 'Book Fair', decision: 'arrangement_rejected', comment: 'Venue too small', decided_by_name: 'Hafiz Ismail', decided_at: '2026-10-08T03:00:00Z' },
      { id: 'h1', event_id: 'e5', event_name: 'Year-End Dinner', decision: 'approved', comment: null, decided_by_name: 'Hafiz Ismail', decided_at: '2026-10-05T03:00:00Z' },
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
    expect(rows[1]).toContain('Hafiz Ismail'); expect(rows[1]).toContain('Venue too small');
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
