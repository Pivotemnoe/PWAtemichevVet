package ru.temichevvet.app;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "NativeReminders")
public class NativeRemindersPlugin extends Plugin {
    @PluginMethod public void sync(PluginCall call) {
        try {
            JSArray items = call.getArray("items", new JSArray());
            int count = ReminderReceiver.replace(getContext(), items);
            JSObject result = new JSObject();
            result.put("scheduled", count);
            call.resolve(result);
        } catch (Exception error) { call.reject("Не удалось обновить напоминания", error); }
    }

    @PluginMethod public void clear(PluginCall call) {
        try { ReminderReceiver.replace(getContext(), new JSArray()); call.resolve(); }
        catch (Exception error) { call.reject("Не удалось отключить напоминания", error); }
    }
}
