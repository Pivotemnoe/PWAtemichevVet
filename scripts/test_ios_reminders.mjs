import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nextIOSReminderDate, planIOSReminders, syncIOSReminders } from '../mobile/ios-reminders.js';

const item = (overrides = {}) => ({ id: 1, title: 'Обработка', due_date: '2026-01-31', due_time: '09:15', periodicity: 'once', ...overrides });
const date = (value) => new Date(value);
const calendar = (value) => [value.getFullYear(), value.getMonth() + 1, value.getDate(), value.getHours(), value.getMinutes()];

test('one-time reminders are future only and keep the chosen local clock', () => {
  assert.deepEqual(calendar(nextIOSReminderDate(item(), date('2026-01-30T12:00:00'))), [2026, 1, 31, 9, 15]);
  assert.equal(nextIOSReminderDate(item(), date('2026-01-31T09:15:00')), null);
});

test('monthly dates clamp in February and return to the original day in March', () => {
  const monthly = item({ periodicity: 'monthly' });
  const feb = nextIOSReminderDate(monthly, date('2026-01-31T09:15:00'));
  assert.deepEqual(calendar(feb), [2026, 2, 28, 9, 15]);
  assert.deepEqual(calendar(nextIOSReminderDate(monthly, feb)), [2026, 3, 31, 9, 15]);
});

test('quarterly, half-yearly and leap-year dates keep the original anchor', () => {
  assert.deepEqual(calendar(nextIOSReminderDate(item({ periodicity: 'every_3_months' }), date('2026-01-31T10:00:00'))), [2026, 4, 30, 9, 15]);
  assert.deepEqual(calendar(nextIOSReminderDate(item({ periodicity: 'every_6_months' }), date('2026-01-31T10:00:00'))), [2026, 7, 31, 9, 15]);
  const leap = item({ due_date: '2024-02-29', periodicity: 'yearly' });
  assert.deepEqual(calendar(nextIOSReminderDate(leap, date('2027-03-01T00:00:00'))), [2028, 2, 29, 9, 15]);
});

test('missed daily and weekly reminders advance without replaying old events', () => {
  assert.deepEqual(calendar(nextIOSReminderDate(item({ periodicity: 'daily' }), date('2026-10-21T09:16:00'))), [2026, 10, 22, 9, 15]);
  assert.deepEqual(calendar(nextIOSReminderDate(item({ periodicity: 'weekly' }), date('2026-10-21T10:00:00'))), [2026, 10, 24, 9, 15]);
});

test('daylight-saving changes preserve the local hour', () => {
  const before = process.env.TZ;
  try {
    process.env.TZ = 'America/New_York';
    const a = item({ due_date: '2026-03-07', periodicity: 'daily' });
    assert.deepEqual(calendar(nextIOSReminderDate(a, date('2026-03-07T09:16:00'))), [2026, 3, 8, 9, 15]);
    const b = item({ due_date: '2026-10-31', periodicity: 'daily' });
    assert.deepEqual(calendar(nextIOSReminderDate(b, date('2026-10-31T09:16:00'))), [2026, 11, 1, 9, 15]);
  } finally { if (before === undefined) delete process.env.TZ; else process.env.TZ = before; }
});

test('ordinary repeating calendars occupy one slot and persist indefinitely', () => {
  const plan = planIOSReminders(['daily', 'weekly', 'monthly', 'yearly'].map((periodicity, i) =>
    item({ id: i + 1, due_date: '2026-01-15', periodicity })), date('2026-10-21T12:00:00'));
  assert.equal(plan.notifications.length, 4);
  assert.equal(plan.info.truncated, false);
  assert.ok(plan.notifications.every((n) => n.schedule.repeats));
  assert.ok(plan.notifications.every((n) => !('year' in n.schedule.on)));
});

test('future repeating dates never schedule before the selected start date', () => {
  const plan = planIOSReminders([item({ due_date: '2027-01-15', periodicity: 'daily' })], date('2026-10-21T12:00:00'));
  assert.equal(plan.notifications.length, 60);
  assert.equal(plan.notifications[0].schedule.repeats, false);
  assert.deepEqual(plan.notifications[0].schedule.on, { year: 2027, month: 1, day: 15, hour: 9, minute: 15 });
  assert.ok(date(plan.info.refreshBefore) > date('2027-03-01'));
});

test('the 60-slot budget keeps the nearest events and reports omitted reminders', () => {
  const items = Array.from({ length: 70 }, (_, i) => item({ id: i + 1, due_date: '2027-01-15' }));
  const plan = planIOSReminders(items.reverse(), date('2026-10-21T12:00:00'));
  assert.equal(plan.notifications.length, 60);
  assert.deepEqual(plan.notifications.map((n) => n.extra.reminderId), Array.from({ length: 60 }, (_, i) => i + 1));
  assert.equal(plan.info.omittedReminders, 10);
  assert.equal(plan.info.truncated, true);
});

test('completed, disabled, expired and duplicate reminders are excluded', () => {
  const plan = planIOSReminders([item(), item({ id: 2, is_active: 0 }), item({ id: 3, is_done: true }),
    item({ id: 4, completed: true }), item({ id: 5 }), item({ id: 5 })], date('2026-01-30T00:00:00'));
  assert.deepEqual(plan.notifications.map((n) => n.extra.reminderId), [1, 5]);
  assert.equal(planIOSReminders([item()], date('2026-02-01')).notifications.length, 0);
});

test('stable notification IDs are independent of input order', () => {
  const a = item({ id: 1, periodicity: 'monthly' });
  const b = item({ id: 2, periodicity: 'yearly', due_date: '2026-02-15' });
  const now = date('2026-10-21');
  assert.deepEqual(planIOSReminders([a, b], now), planIOSReminders([b, a], now));
  const ids = planIOSReminders([a, b], now).notifications.map((n) => n.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.every((id) => id > 0 && id <= 2147483647));
});

test('invalid input is rejected before replacing the native plan', async () => {
  let changed = false;
  const plugin = { replace: async () => { changed = true; } };
  for (const overrides of [{ due_date: '2026-02-31' }, { due_time: '25:00' }, { periodicity: 'unknown' }]) {
    await assert.rejects(syncIOSReminders(plugin, [item(overrides)], date('2026-01-01')), /invalid_reminder_date/);
  }
  assert.equal(changed, false);
  assert.throws(() => nextIOSReminderDate(item(), new Date('invalid')), /invalid_reminder_clock/);
  assert.throws(() => planIOSReminders(null), /invalid_reminder_list/);
});

test('native scheduling errors propagate; an empty plan also clears old reminders', async () => {
  await assert.rejects(syncIOSReminders({ replace: async () => { throw new Error('OS refused'); } }, [], date('2026-01-01')), /OS refused/);
  let received;
  const info = await syncIOSReminders({ replace: async (value) => { received = value; } }, [], date('2026-01-01'));
  assert.deepEqual(received, { notifications: [] });
  assert.equal(info.scheduled, 0);
});
