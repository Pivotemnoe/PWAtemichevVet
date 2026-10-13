package ru.temichevvet.app;

import org.junit.Test;
import static org.junit.Assert.assertEquals;
import java.text.SimpleDateFormat;
import java.util.TimeZone;

public class ReminderCalendarTest {
    private final TimeZone utc = TimeZone.getTimeZone("UTC");
    private long instant(String value) throws Exception {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd HH:mm");
        format.setTimeZone(utc);
        return format.parse(value).getTime();
    }
    @Test public void monthlyDateReturnsToOriginalDayAfterFebruary() throws Exception {
        assertEquals(instant("2027-02-28 09:00"), ReminderCalendar.next("2027-01-31", null, "monthly", instant("2027-02-01 00:00"), utc));
        assertEquals(instant("2027-03-31 09:00"), ReminderCalendar.next("2027-01-31", null, "monthly", instant("2027-03-01 00:00"), utc));
    }
    @Test public void leapYearAndQuarterlyDatesRemainAnchored() throws Exception {
        assertEquals(instant("2025-02-28 10:30"), ReminderCalendar.next("2024-02-29", "10:30", "yearly", instant("2025-01-01 00:00"), utc));
        assertEquals(instant("2028-02-29 10:30"), ReminderCalendar.next("2024-02-29", "10:30", "yearly", instant("2028-01-01 00:00"), utc));
        assertEquals(instant("2027-04-30 09:00"), ReminderCalendar.next("2027-01-31", null, "every_3_months", instant("2027-02-01 00:00"), utc));
        assertEquals(instant("2027-07-31 09:00"), ReminderCalendar.next("2027-01-31", null, "every_6_months", instant("2027-02-01 00:00"), utc));
    }
    @Test public void missedDailyAndWeeklyDatesSkipPastOccurrences() throws Exception {
        assertEquals(instant("2027-01-06 09:00"), ReminderCalendar.next("2027-01-01", null, "daily", instant("2027-01-05 09:00"), utc));
        assertEquals(instant("2027-01-15 09:00"), ReminderCalendar.next("2027-01-01", null, "weekly", instant("2027-01-10 09:00"), utc));
    }
    @Test public void onceDoesNotRepeatAndInvalidDatesAreRejected() throws Exception {
        assertEquals(0, ReminderCalendar.next("2027-01-01", null, "once", instant("2027-01-01 09:00"), utc));
        assertEquals(0, ReminderCalendar.next("2027-02-30", null, "monthly", instant("2027-01-01 00:00"), utc));
        assertEquals(0, ReminderCalendar.next("bad-date", null, "daily", 0, utc));
    }
    @Test public void localTimeSurvivesDaylightSavingChange() throws Exception {
        TimeZone berlin = TimeZone.getTimeZone("Europe/Berlin");
        assertEquals(instant("2027-03-28 07:00"), ReminderCalendar.next("2027-03-27", "09:00", "daily", instant("2027-03-27 12:00"), berlin));
        assertEquals(instant("2027-03-29 00:30"), ReminderCalendar.next("2027-03-27", "02:30", "daily", instant("2027-03-28 12:00"), berlin));
        assertEquals(instant("2027-03-29 00:30"), ReminderCalendar.next("2027-03-28", "02:30", "daily", instant("2027-03-28 12:00"), berlin));
    }
}
