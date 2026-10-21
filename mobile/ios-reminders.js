// Pure calendar planning; the iOS bridge submits the result to UserNotifications.
const monthIntervals = { monthly: 1, every_3_months: 3, every_6_months: 6, yearly: 12 };
const supported = new Set(['once', 'daily', 'weekly', ...Object.keys(monthIntervals)]);

function anchor(item) {
  const date = /^(\d{4})-(\d{2})-(\d{2})$/.exec(item.due_date || '');
  const time = /^(\d{2}):(\d{2})$/.exec(item.due_time || '09:00');
  if (!date || !time) throw new Error('invalid_reminder_date');
  const [year, month, day] = date.slice(1).map(Number);
  const [hour, minute] = time.slice(1).map(Number);
  const start = new Date(year, month - 1, day, hour, minute);
  const periodicity = item.periodicity || 'once';
  if (year < 100 || month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59
      || start.getFullYear() !== year || start.getMonth() !== month - 1 || start.getDate() !== day
      || !supported.has(periodicity)) throw new Error('invalid_reminder_date');
  return { year, month: month - 1, day, hour, minute, start, periodicity };
}

export function nextIOSReminderDate(item, after = new Date()) {
  if (!(after instanceof Date) || !Number.isFinite(after.getTime())) throw new Error('invalid_reminder_clock');
  const a = anchor(item);
  if (a.start > after) return a.start;
  if (a.periodicity === 'once') return null;
  const days = a.periodicity === 'daily' ? 1 : a.periodicity === 'weekly' ? 7 : 0;
  if (days) {
    let periods = Math.max(0, Math.floor((after - a.start) / (86400000 * days)));
    for (;;) {
      const next = new Date(a.year, a.month, a.day + periods * days, a.hour, a.minute);
      if (next > after) return next;
      periods++;
    }
  }
  const months = monthIntervals[a.periodicity];
  let periods = Math.max(0, Math.floor(((after.getFullYear() - a.year) * 12 + after.getMonth() - a.month) / months));
  for (;;) {
    const first = new Date(a.year, a.month + periods * months, 1, a.hour, a.minute);
    const lastDay = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    const next = new Date(first.getFullYear(), first.getMonth(), Math.min(a.day, lastDay), a.hour, a.minute);
    if (next > after) return next;
    periods++;
  }
}

function repeatingSchedule(a, now) {
  // A repeating calendar trigger must never run before the owner's start date.
  if (a.start > now) return null;
  const time = { hour: a.hour, minute: a.minute };
  if (a.periodicity === 'daily') return { on: time, repeats: true };
  if (a.periodicity === 'weekly') return { on: { ...time, weekday: a.start.getDay() + 1 }, repeats: true };
  if (a.periodicity === 'monthly' && a.day <= 28) return { on: { ...time, day: a.day }, repeats: true };
  if (a.periodicity === 'yearly' && !(a.month === 1 && a.day === 29)) {
    return { on: { ...time, month: a.month + 1, day: a.day }, repeats: true };
  }
  return null;
}

function stableId(value, used) {
  let hash = 2166136261;
  for (const character of value) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  let id = (hash >>> 0) % 2147483646 + 1;
  while (used.has(id)) id = id % 2147483646 + 1;
  used.add(id);
  return id;
}

export function planIOSReminders(items, now = new Date(), limit = 60) {
  if (!Array.isArray(items)) throw new Error('invalid_reminder_list');
  if (!(now instanceof Date) || !Number.isFinite(now.getTime())) throw new Error('invalid_reminder_clock');
  if (!Number.isInteger(limit) || limit < 1 || limit > 60) throw new Error('invalid_reminder_limit');
  const seen = new Set();
  const candidates = [];
  for (const item of items) {
    if (!Number.isSafeInteger(item.id) || item.id < 1 || seen.has(item.id) || item.is_done || item.completed
        || (item.is_active !== undefined && !Number(item.is_active))) continue;
    seen.add(item.id);
    const next = nextIOSReminderDate(item, now);
    if (next) candidates.push({ item, next, repeat: repeatingSchedule(anchor(item), now) });
  }
  const notifications = [];
  const used = new Set();
  const planned = new Set();
  while (candidates.length && notifications.length < limit) {
    candidates.sort((a, b) => a.next - b.next || a.item.id - b.item.id);
    const current = candidates.shift();
    const { item, next, repeat } = current;
    const on = { year: next.getFullYear(), month: next.getMonth() + 1, day: next.getDate(), hour: next.getHours(), minute: next.getMinutes() };
    const key = repeat ? `repeat:${item.id}` : `date:${item.id}:${JSON.stringify(on)}`;
    notifications.push({
      id: stableId(key, used), title: 'TemichevVet', body: String(item.title || 'Важная дата питомца'),
      schedule: repeat || { on, repeats: false },
      extra: { tvvPetReminder: true, reminderId: item.id },
    });
    planned.add(item.id);
    if (!repeat) {
      current.next = nextIOSReminderDate(item, next);
      if (current.next) candidates.push(current);
    }
  }
  candidates.sort((a, b) => a.next - b.next || a.item.id - b.item.id);
  return {
    notifications,
    info: { scheduled: notifications.length, truncated: candidates.length > 0,
      refreshBefore: candidates[0]?.next.toISOString() || null,
      omittedReminders: new Set(candidates.filter((x) => !planned.has(x.item.id)).map((x) => x.item.id)).size },
  };
}

export async function syncIOSReminders(plugin, items, now = new Date()) {
  // Validate every date before replacing any existing schedule.
  const plan = planIOSReminders(items, now);
  await plugin.replace({ notifications: plan.notifications });
  return plan.info;
}
