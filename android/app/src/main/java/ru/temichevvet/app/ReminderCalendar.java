package ru.temichevvet.app;

import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.TimeZone;

/** Calendar recurrence anchored to the original date, without February/month-end drift. */
final class ReminderCalendar {
    static long next(String date, String time, String periodicity, long after, TimeZone zone) {
        if (date == null || !date.matches("\\d{4}-\\d{2}-\\d{2}")) return 0;
        if (time == null || !time.matches("([01]\\d|2[0-3]):[0-5]\\d")) time = "09:00";
        int hour = Integer.parseInt(time.substring(0, 2));
        int minute = Integer.parseInt(time.substring(3, 5));
        Calendar anchor = new GregorianCalendar(zone);
        anchor.clear();
        anchor.setLenient(false);
        try {
            anchor.set(Integer.parseInt(date.substring(0, 4)), Integer.parseInt(date.substring(5, 7)) - 1,
                Integer.parseInt(date.substring(8, 10)), 12, 0);
            anchor.getTimeInMillis(); // Validate the calendar date before normalizing any DST gap.
            anchor.setLenient(true);
            anchor.set(Calendar.HOUR_OF_DAY, hour);
            anchor.set(Calendar.MINUTE, minute);
            if (anchor.getTimeInMillis() > after) return anchor.getTimeInMillis();
        } catch (IllegalArgumentException invalidDate) { return 0; }
        int days = "daily".equals(periodicity) ? 1 : "weekly".equals(periodicity) ? 7 : 0;
        int months = "monthly".equals(periodicity) ? 1 : "every_3_months".equals(periodicity) ? 3
            : "every_6_months".equals(periodicity) ? 6 : "yearly".equals(periodicity) ? 12 : 0;
        if (days == 0 && months == 0) return 0;
        Calendar current = new GregorianCalendar(zone);
        current.setTimeInMillis(after);
        long count = days > 0
            ? Math.max(0, (after - anchor.getTimeInMillis()) / 86400000L / days - 1)
            : Math.max(0, ((current.get(Calendar.YEAR) - anchor.get(Calendar.YEAR)) * 12L
                + current.get(Calendar.MONTH) - anchor.get(Calendar.MONTH)) / months - 1);
        for (; count < Integer.MAX_VALUE / Math.max(days, months); count++) {
            Calendar candidate = (Calendar) anchor.clone();
            // A DST gap may shift this occurrence; later dates retain the requested time.
            candidate.setLenient(true);
            if (days > 0) candidate.add(Calendar.DAY_OF_MONTH, (int) count * days);
            else {
                candidate.set(Calendar.DAY_OF_MONTH, 1);
                candidate.add(Calendar.MONTH, (int) count * months);
                candidate.set(Calendar.DAY_OF_MONTH, Math.min(anchor.get(Calendar.DAY_OF_MONTH), candidate.getActualMaximum(Calendar.DAY_OF_MONTH)));
            }
            candidate.set(Calendar.HOUR_OF_DAY, hour);
            candidate.set(Calendar.MINUTE, minute);
            if (candidate.getTimeInMillis() > after) return candidate.getTimeInMillis();
        }
        return 0;
    }
}
