// CR-103 / CR-104: shared safety decision display rules.
import { describe, expect, it } from 'vitest';
async function helper() {
  const modules = import.meta.glob('../safetyDecision.js');
  expect(modules['../safetyDecision.js'], 'shared safety formatter exists').toBeTypeOf('function');
  return modules['../safetyDecision.js']();
}
describe('safety decision display', () => {
  it('formats an instant in Singapore for every safety screen', async () => {
    const { displaySafetyTime } = await helper();
    expect(displaySafetyTime('2026-10-08T20:00:00Z')).toBe('9 Oct 2026, 4:00 am');
  });
  it('shows missing timestamps honestly', async () => {
    const { displaySafetyTime } = await helper();
    expect(displaySafetyTime(null)).toBe('Not provided'); expect(displaySafetyTime(undefined)).toBe('Not provided');
  });
});
