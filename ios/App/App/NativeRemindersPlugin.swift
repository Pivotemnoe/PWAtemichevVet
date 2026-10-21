import Capacitor
import UserNotifications

// LocalNotifications still owns permissions and tap events. This adapter saves
// calendar triggers with the correct repeats flag and awaits every native write.
@objc(NativeRemindersPlugin)
public class NativeRemindersPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "NativeRemindersPlugin"
    public let jsName = "NativeReminders"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "replace", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clear", returnType: CAPPluginReturnPromise)
    ]
    private let queue = DispatchQueue(label: "ru.temichevvet.reminders")
    private static let prefix = "tvv-reminder-"

    private func requests(_ items: [JSObject]) throws -> [UNNotificationRequest] {
        var ids = Set<Int>()
        return try items.map { item in
            guard let id = item["id"] as? Int, id > 0, id <= Int(Int32.max), ids.insert(id).inserted,
                  let schedule = item["schedule"] as? JSObject,
                  let on = schedule["on"] as? JSObject,
                  let repeats = schedule["repeats"] as? Bool,
                  let extra = item["extra"] as? JSObject,
                  extra["tvvPetReminder"] as? Bool == true else { throw ReminderError.invalid }
            var components = DateComponents()
            components.calendar = Calendar(identifier: .gregorian)
            let ranges: [String: ClosedRange<Int>] = ["year": 100...9999, "month": 1...12,
                "day": 1...31, "hour": 0...23, "minute": 0...59, "weekday": 1...7]
            for key in on.keys {
                guard let range = ranges[key], let value = on[key] as? Int, range.contains(value) else {
                    throw ReminderError.invalid
                }
                switch key {
                case "year": components.year = value
                case "month": components.month = value
                case "day": components.day = value
                case "hour": components.hour = value
                case "minute": components.minute = value
                case "weekday": components.weekday = value
                default: break
                }
            }
            guard components.hour != nil, components.minute != nil,
                  repeats || (components.year != nil && components.month != nil && components.day != nil) else {
                throw ReminderError.invalid
            }
            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: repeats)
            guard trigger.nextTriggerDate() != nil else { throw ReminderError.expired }
            let content = UNMutableNotificationContent()
            content.title = String((item["title"] as? String ?? "TemichevVet").prefix(200))
            content.body = String((item["body"] as? String ?? "Важная дата питомца").prefix(1000))
            content.sound = .default
            content.threadIdentifier = "pet-dates"
            content.userInfo = ["cap_extra": extra, "cap_schedule": schedule]
            return UNNotificationRequest(identifier: Self.prefix + String(id), content: content, trigger: trigger)
        }
    }

    @objc func replace(_ call: CAPPluginCall) {
        guard let items = call.getArray("notifications", JSObject.self), items.count <= 60 else {
            call.reject("invalid_reminder_plan")
            return
        }
        let next: [UNNotificationRequest]
        do { next = try requests(items) } catch {
            call.reject("invalid_reminder_plan", nil, error)
            return
        }
        queue.async {
            let center = UNUserNotificationCenter.current()
            center.getPendingNotificationRequests { pending in
                let previous = pending.filter { $0.identifier.hasPrefix(Self.prefix) }
                guard pending.count - previous.count + next.count <= 64 else {
                    call.reject("reminder_capacity_exceeded")
                    return
                }
                // All triggers have been validated before touching the old plan.
                // Remove obsolete requests first so iOS never silently evicts a
                // valid reminder while the old and new plans overlap its limit.
                let nextIDs = Set(next.map { $0.identifier })
                center.removePendingNotificationRequests(withIdentifiers:
                    previous.filter { !nextIDs.contains($0.identifier) }.map { $0.identifier })
                self.add(next, center: center) { error in
                    guard let error = error else { call.resolve(["scheduled": next.count]); return }
                    center.removePendingNotificationRequests(withIdentifiers: next.map { $0.identifier })
                    self.add(previous, center: center) { rollbackError in
                        call.reject(rollbackError == nil ? "reminder_schedule_failed" : "reminder_restore_failed", nil, error)
                    }
                }
            }
        }
    }

    private func add(_ requests: [UNNotificationRequest], center: UNUserNotificationCenter,
                     completion: @escaping (Error?) -> Void) {
        // Sequential writes make failure recovery deterministic.
        guard let first = requests.first else { completion(nil); return }
        center.add(first) { error in
            if let error = error { completion(error) }
            else { self.add(Array(requests.dropFirst()), center: center, completion: completion) }
        }
    }

    @objc func clear(_ call: CAPPluginCall) {
        UNUserNotificationCenter.current().getPendingNotificationRequests { pending in
            let ours = pending.filter { $0.identifier.hasPrefix(Self.prefix) }.map { $0.identifier }
            UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ours)
            call.resolve()
        }
    }

    private enum ReminderError: Error { case invalid, expired }
}
