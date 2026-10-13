package ru.temichevvet.app;

import android.Manifest;
import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.HashSet;
import java.util.Set;
import java.util.TimeZone;

/** Local-only alarms. No network request or credentials are used by this receiver. */
public class ReminderReceiver extends BroadcastReceiver {
    private static final String CHANNEL = "tvv_pet_dates";
    private static final String STORE = "tvv_pet_dates";
    private static final Object LOCK = new Object();
    private static final String ACTION = "ru.temichevvet.app.REMINDER";

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(STORE, Context.MODE_PRIVATE);
    }
    private static JSONArray read(Context context) {
        try { return new JSONArray(preferences(context).getString("items", "[]")); }
        catch (Exception malformed) { return new JSONArray(); }
    }
    private static PendingIntent alarmIntent(Context context, int id, long at) {
        Intent intent = new Intent(context, ReminderReceiver.class).setAction(ACTION);
        intent.putExtra("id", id).putExtra("scheduled_at", at);
        return PendingIntent.getBroadcast(context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    private static long next(JSONObject item, long after) {
        return ReminderCalendar.next(item.optString("due_date"), item.optString("due_time", "09:00"),
            item.optString("periodicity", "once"), after, TimeZone.getDefault());
    }
    private static boolean allowed(Context context) {
        return (Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)
            && NotificationManagerCompat.from(context).areNotificationsEnabled();
    }
    private static void schedule(Context context, JSONObject item) {
        long at = item.optLong("next_at");
        if (at <= 0 || !allowed(context)) return;
        // Inexact date reminders work without special exact-alarm access, also during idle.
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, alarmIntent(context, item.optInt("id"), at));
    }
    static int replace(Context context, JSONArray incoming) throws Exception {
        synchronized (LOCK) {
            JSONArray old = read(context);
            Set<Integer> incomingIds = new HashSet<>();
            JSONArray stored = new JSONArray();
            long now = System.currentTimeMillis();
            for (int i = 0; i < incoming.length(); i++) {
                JSONObject source = incoming.optJSONObject(i);
                if (source == null) continue;
                long id = source.optLong("id");
                if (id < 1 || id > Integer.MAX_VALUE || source.optBoolean("is_done") || source.optBoolean("completed")
                    || (source.has("is_active") && source.optInt("is_active", 1) == 0) || !incomingIds.add((int) id)) continue;
                JSONObject item = new JSONObject();
                item.put("id", id).put("title", source.optString("title", "Важная дата питомца"))
                    .put("due_date", source.optString("due_date")).put("due_time", source.optString("due_time", "09:00"))
                    .put("periodicity", source.optString("periodicity", "once"));
                item.put("next_at", next(item, now));
                if (item.optLong("next_at") > 0) stored.put(item);
            }
            AlarmManager alarms = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
            for (int i = 0; i < old.length(); i++) {
                int id = old.getJSONObject(i).optInt("id");
                alarms.cancel(alarmIntent(context, id, 0));
                if (!incomingIds.contains(id)) NotificationManagerCompat.from(context).cancel("tvv_pet_date", id);
            }
            if (!preferences(context).edit().putString("items", stored.toString()).commit()) throw new IllegalStateException("reminder_store_failed");
            createChannel(context);
            for (int i = 0; i < stored.length(); i++) schedule(context, stored.getJSONObject(i));
            return stored.length();
        }
    }
    private static void createChannel(Context context) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "Важные даты питомца", NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("Сохранённые напоминания о питомцах");
            channel.setLockscreenVisibility(NotificationCompat.VISIBILITY_PRIVATE);
            ((NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }
    @Override public void onReceive(Context context, Intent intent) {
        synchronized (LOCK) {
            try {
                if (!ACTION.equals(intent.getAction())) {
                    // Recalculate local wall-clock dates after boot, update, or time-zone change.
                    replace(context, read(context));
                    return;
                }
                int id = intent.getIntExtra("id", 0);
                long expected = intent.getLongExtra("scheduled_at", 0);
                JSONArray items = read(context);
                for (int i = 0; i < items.length(); i++) {
                    JSONObject item = items.getJSONObject(i);
                    if (item.optInt("id") != id || expected <= 0 || item.optLong("next_at") != expected) continue;
                    long now = System.currentTimeMillis();
                    if (now < expected) { schedule(context, item); return; }
                    item.put("next_at", next(item, Math.max(now, expected)));
                    if (!preferences(context).edit().putString("items", items.toString()).commit()) return;
                    schedule(context, item);
                    if (!allowed(context)) return;
                    createChannel(context);
                    Intent open = new Intent(context, MainActivity.class).setAction(Intent.ACTION_VIEW)
                        .setData(Uri.parse("temichevvet://reminders"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                    PendingIntent content = PendingIntent.getActivity(context, id, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                    NotificationCompat.Builder notification = new NotificationCompat.Builder(context, CHANNEL)
                        .setSmallIcon(R.drawable.ic_stat_paw).setColor(0xff1476d4).setContentTitle("TemichevVet")
                        .setContentText(item.optString("title", "Важная дата питомца"))
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(item.optString("title")))
                        .setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setAutoCancel(true).setContentIntent(content);
                    NotificationManagerCompat.from(context).notify("tvv_pet_date", id, notification.build());
                    return;
                }
            } catch (Exception ignored) {
                // Preserve stored dates for the next successful sync; no private data in logs.
            }
        }
    }
}
