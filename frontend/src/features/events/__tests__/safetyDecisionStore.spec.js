// CR-103 / CR-104: safety queue, review and decision state.
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, eventsApi } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
vi.mock('@/services/api', async (original) => ({
  ...(await original()),
  eventsApi: { safetyQueue: vi.fn(), safetyHistory: vi.fn(), safetyReview: vi.fn(), safetyApprove: vi.fn(), safetyRequestChanges: vi.fn(), safetyReject: vi.fn() },
}));
async function store() {
  const modules = import.meta.glob('../safetyDecisionStore.js');
  expect(modules['../safetyDecisionStore.js'], 'safetyDecisionStore exists').toBeTypeOf('function');
  const { useSafetyDecisionStore } = await modules['../safetyDecisionStore.js']();
  return useSafetyDecisionStore();
}
const review = { event: { id: 'e1' }, decisions: [{ id: 'd1' }], venues: [], equipment_lines: [] };
describe('safetyDecisionStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia()); vi.resetAllMocks(); localStorage.clear();
    useAuthStore().token = 'access'; useAuthStore().profile = { role: 'safety_officer' };
    eventsApi.safetyQueue.mockResolvedValue({ items: [{ event_id: 'e1' }] });
    eventsApi.safetyReview.mockResolvedValue(review);
    eventsApi.safetyHistory.mockResolvedValue({ items: [{ id: 'h1', decision: 'approved' }] });
  });
  it('CR-103 AC7 loads the recent decisions', async () => {
    const s = await store(); await s.loadHistory();
    expect(eventsApi.safetyHistory).toHaveBeenCalledWith('access');
    expect(s.history).toEqual([{ id: 'h1', decision: 'approved' }]); expect(s.historyError).toBeNull();
  });
  it('CR-103 AC7 clears the history on failure without touching the queue', async () => {
    const s = await store(); await s.loadQueue(); await s.loadHistory();
    eventsApi.safetyHistory.mockRejectedValue(new Error('History unavailable'));
    await s.loadHistory();
    expect(s.history).toEqual([]); expect(s.historyError).toBe('History unavailable');
    expect(s.queue).toEqual([{ event_id: 'e1' }]); expect(s.error).toBeNull();
  });
  it('loads the queue and review with their decisions', async () => {
    const s = await store(); await s.loadQueue(); await s.loadReview('e1');
    expect(s.$id).toBe('safetyDecision');
    expect(s.queue).toEqual([{ event_id: 'e1' }]); expect(s.review).toEqual(review);
    expect(s.decisions).toEqual([{ id: 'd1' }]); expect(s.loading).toBe(false); expect(s.error).toBeNull();
    expect(eventsApi.safetyReview).toHaveBeenCalledWith('e1', 'access');
  });
  it('clears stale queue and review on failed reads', async () => {
    const s = await store(); await s.loadQueue(); await s.loadReview('e1');
    eventsApi.safetyQueue.mockRejectedValue(new Error('Queue unavailable'));
    await s.loadQueue(); expect(s.queue).toEqual([]); expect(s.error).toBe('Queue unavailable');
    eventsApi.safetyReview.mockRejectedValue(new Error('Review unavailable'));
    await s.loadReview('e2'); expect(s.review).toBeNull(); expect(s.decisions).toEqual([]);
    expect(s.error).toBe('Review unavailable'); expect(s.loading).toBe(false);
  });
  it.each([['approve', 'safetyApprove'], ['requestChanges', 'safetyRequestChanges'], ['reject', 'safetyReject']])('posts %s and refreshes after a successful decision', async (kind, api) => {
    const s = await store(); await s.loadReview('e1');
    eventsApi[api].mockResolvedValue({ id: 'e1', status: 'planning' });
    const body = { comment: 'Move the chairs', booking_ids: ['b1'], equipment_request_ids: ['q1'] };
    await expect(s.decide(kind, 'e1', body)).resolves.toEqual({ id: 'e1', status: 'planning' });
    expect(eventsApi[api]).toHaveBeenCalledWith('e1', body, 'access');
    expect(eventsApi.safetyQueue).toHaveBeenCalledTimes(1); expect(eventsApi.safetyReview).toHaveBeenCalledTimes(1);
    expect(s.review).toBeNull(); expect(s.decisions).toEqual([]);
    expect(s.loading).toBe(false);
  });
  it.each([409, 422])('preserves the server %s message without refreshing', async (status) => {
    const s = await store(); eventsApi.safetyApprove.mockRejectedValue(new ApiError('Arrangements changed', status));
    await expect(s.decide('approve', 'e1', {})).rejects.toThrow('Arrangements changed');
    expect(s.error).toBe('Arrangements changed'); expect(s.loading).toBe(false);
    expect(eventsApi.safetyQueue).not.toHaveBeenCalled();
  });
  it('does not turn a successful decision into failure when refresh fails', async () => {
    const s = await store(); eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    eventsApi.safetyReview.mockRejectedValue(new ApiError('Event is no longer in review', 404));
    eventsApi.safetyQueue.mockRejectedValue(new Error('Offline'));
    await expect(s.decide('approve', 'e1', {})).resolves.toEqual({ id: 'e1', status: 'confirmed' });
    expect(s.review).toBeNull(); expect(s.loading).toBe(false);
  });
  it('sends no reads or decisions without a session', async () => {
    useAuthStore().token = null; const s = await store();
    await s.loadQueue(); await s.loadReview('e1'); await expect(s.decide('approve', 'e1', {})).rejects.toThrow();
    Object.values(eventsApi).forEach((call) => expect(call).not.toHaveBeenCalled());
  });
  it('drops a slower review success after navigating to another event', async () => {
    let resolve; eventsApi.safetyReview.mockImplementationOnce(() => new Promise((r) => { resolve = r; }));
    const s = await store(); const pending = s.loadReview('e1');
    eventsApi.safetyReview.mockResolvedValue({ ...review, event: { id: 'e2' }, decisions: [{ id: 'd2' }] });
    await s.loadReview('e2'); resolve(review); await pending;
    expect(s.review.event.id).toBe('e2'); expect(s.decisions).toEqual([{ id: 'd2' }]);
  });
  it('drops a slower review failure and keeps newer loading state', async () => {
    let rejectOld; let resolveNew;
    eventsApi.safetyReview.mockImplementationOnce(() => new Promise((_, r) => { rejectOld = r; }))
      .mockImplementationOnce(() => new Promise((r) => { resolveNew = r; }));
    const s = await store(); const old = s.loadReview('e1'); const newer = s.loadReview('e2');
    rejectOld(new Error('Old failure')); await old;
    expect(s.error).toBeNull(); expect(s.loading).toBe(true);
    resolveNew({ ...review, event: { id: 'e2' } }); await newer; expect(s.review.event.id).toBe('e2');
  });
  it('does not restore private review after the active role changes', async () => {
    let resolve; eventsApi.safetyReview.mockImplementationOnce(() => new Promise((r) => { resolve = r; }));
    const s = await store(); const pending = s.loadReview('e1'); useAuthStore().profile.role = 'event_organiser';
    resolve(review); await pending; expect(s.review).toBeNull(); expect(s.decisions).toEqual([]);
  });

  it('rejects the original A response after navigation A to B to A', async () => {
    let resolveA; eventsApi.safetyReview.mockImplementationOnce(() => new Promise((r) => { resolveA = r; }));
    const s = await store(); const originalA = s.loadReview('e1');
    eventsApi.safetyReview.mockResolvedValue({ ...review, event: { id: 'e2' } }); await s.loadReview('e2');
    eventsApi.safetyReview.mockResolvedValue({ ...review, event: { id: 'e1', name: 'Latest A' }, decisions: [{ id: 'latest' }] });
    await s.loadReview('e1'); resolveA(review); await originalA;
    expect(s.review.event.name).toBe('Latest A'); expect(s.decisions).toEqual([{ id: 'latest' }]);
  });
  it('ignores original A failure while the newest A is still loading', async () => {
    let rejectA; let resolveLatest;
    eventsApi.safetyReview.mockImplementationOnce(() => new Promise((_, r) => { rejectA = r; }));
    const s = await store(); const original = s.loadReview('e1');
    await s.loadReview('e2');
    eventsApi.safetyReview.mockImplementationOnce(() => new Promise((r) => { resolveLatest = r; }));
    const latest = s.loadReview('e1'); rejectA(new Error('Original A failure')); await original;
    expect(s.error).toBeNull(); expect(s.loading).toBe(true);
    resolveLatest(review); await latest; expect(s.review).toEqual(review);
  });
  it('invalidates a pending review read when a decision succeeds', async () => {
    let resolve; eventsApi.safetyReview.mockImplementationOnce(() => new Promise((r) => { resolve = r; }));
    const s = await store(); const pending = s.loadReview('e1');
    eventsApi.safetyApprove.mockResolvedValue({ id: 'e1', status: 'confirmed' });
    await s.decide('approve', 'e1', { comment: null }); resolve(review); await pending;
    expect(s.review).toBeNull(); expect(s.decisions).toEqual([]); expect(s.error).toBeNull();
  });

});
