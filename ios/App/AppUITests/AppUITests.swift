import XCTest
import Foundation

final class AppUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "ru.temichevvet.app.qa")

    override func setUpWithError() throws {
        continueAfterFailure = false
        _ = try qaRequest("/mobile/qa-api-state", body: ["unavailable": false])
        app.launch()
        // Feature tests must still run when the separate login test failed;
        // obtain a session through the same visible UI, never by injecting it.
        if !name.contains("test01") && !name.contains("test02") {
            let ready = NSPredicate { _, _ in
                self.app.buttons["Войти или создать аккаунт"].exists ||
                self.app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Лео iOS")).firstMatch.exists
            }
            expectation(for: ready, evaluatedWith: nil)
            waitForExpectations(timeout: 40)
            if app.buttons["Войти или создать аккаунт"].exists { try signIn() }
        }
    }

    override func tearDownWithError() throws {
        let screen = XCTAttachment(screenshot: app.screenshot())
        screen.name = name
        screen.lifetime = .keepAlways
        add(screen)
        let tree = XCTAttachment(string: app.debugDescription)
        tree.name = "Accessibility - " + name
        tree.lifetime = .keepAlways
        add(tree)
    }

    private func tapButton(_ label: String, file: StaticString = #filePath, line: UInt = #line) {
        let buttons = app.buttons.matching(NSPredicate(format: "label == %@", label))
        XCTAssertTrue(buttons.firstMatch.waitForExistence(timeout: 15), label, file: file, line: line)
        for _ in 0..<8 {
            if let button = buttons.allElementsBoundByIndex.first(where: { $0.isHittable }) {
                button.tap()
                return
            }
            scrollToward(buttons.firstMatch)
        }
        XCTFail("Button is not reachable: " + label, file: file, line: line)
    }

    private func tapButtonBeginning(_ label: String) {
        let button = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", label)).firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: 15), label)
        for _ in 0..<8 {
            if button.isHittable { button.tap(); return }
            scrollToward(button)
        }
        XCTFail("Button is not reachable: " + label)
    }

    private func scrollToward(_ element: XCUIElement) {
        // WebKit may restore the previous scroll position after a cold launch.
        // A control above the fixed header needs a downward gesture, whereas
        // one below the bottom bar needs an upward gesture.
        if element.frame.midY < app.frame.midY { app.swipeDown() }
        else { app.swipeUp() }
    }

    private func qaRequest(_ path: String, body: [String: Any]? = nil) throws -> [String: Any] {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8096" + path)!)
        request.timeoutInterval = 15
        if let body = body {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let semaphore = DispatchSemaphore(value: 0)
        var output: Data?
        var failure: Error?
        var status = 0
        URLSession.shared.dataTask(with: request) { data, response, error in
            output = data; failure = error; status = (response as? HTTPURLResponse)?.statusCode ?? 0
            semaphore.signal()
        }.resume()
        XCTAssertEqual(semaphore.wait(timeout: .now() + 20), .success)
        if let failure = failure { throw failure }
        XCTAssertEqual(status, 200)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(output)) as? [String: Any])
    }

    private func openPet() {
        tapButton("Питомцы")
        let pet = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Лео iOS")).firstMatch
        XCTAssertTrue(pet.waitForExistence(timeout: 15))
        tapButton("Открыть карточку")
    }

    func test01GuestShell() {
        // The hosted simulator's first WebKit launch can finish after its
        // accessibility snapshot is ready; subsequent launches are much faster.
        XCTAssertTrue(app.buttons["Войти или создать аккаунт"].waitForExistence(timeout: 60))
        for label in ["Главная", "Питомцы", "Здоровье", "Даты", "Ещё"] {
            XCTAssertTrue(app.buttons[label].exists, "Missing app tab: " + label)
        }
        XCTAssertTrue(app.buttons["Войти или создать аккаунт"].exists)
    }

    private func signIn() throws {
        tapButton("Войти или создать аккаунт")
        let email = app.textFields["Электронная почта"]
        XCTAssertTrue(email.waitForExistence(timeout: 10))
        email.tap()
        email.typeText("ios-qa@example.ru")
        let consent = app.checkBoxes.firstMatch.exists ? app.checkBoxes.firstMatch :
            app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Я согласен с условиями сервиса.")).firstMatch
        XCTAssertTrue(consent.exists)
        consent.tap()
        tapButton("Получить код")
        let hint = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Тестовый код:")).firstMatch
        XCTAssertTrue(hint.waitForExistence(timeout: 20))
        let expression = try NSRegularExpression(pattern: "[0-9]{6}")
        let text = hint.label
        let match = try XCTUnwrap(expression.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)))
        let range = try XCTUnwrap(Range(match.range, in: text))
        let code = app.textFields["Код"]
        XCTAssertTrue(code.exists)
        code.tap()
        code.typeText(String(text[range]))
        tapButton("Войти")
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Лео iOS")).firstMatch.waitForExistence(timeout: 25))
    }

    func test02EmailLoginAndTabs() throws {
        try signIn()
        for label in ["Питомцы", "Здоровье", "Даты", "Ещё", "Главная"] {
            tapButton(label)
            XCTAssertTrue(app.buttons["Главная"].exists)
        }
    }

    func test03OfflineNoteSurvivesColdStartAndSyncsOnce() throws {
        openPet()
        tapButtonBeginning("Наблюдения")
        _ = try qaRequest("/mobile/qa-api-state", body: ["unavailable": true])
        defer { _ = try? qaRequest("/mobile/qa-api-state", body: ["unavailable": false]) }
        let note = app.textFields["Что заметили?"]
        XCTAssertTrue(note.waitForExistence(timeout: 10))
        note.tap()
        note.typeText("QA iOS offline 20261021")
        tapButton("Добавить наблюдение")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "QA iOS offline 20261021")).firstMatch.waitForExistence(timeout: 15))
        XCTAssertEqual(try qaRequest("/mobile/qa-api-state")["ios_offline_note_count"] as? Int, 0)
        app.terminate()
        app.launch()
        openPet()
        tapButtonBeginning("Наблюдения")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "QA iOS offline 20261021")).firstMatch.waitForExistence(timeout: 20))
        tapButton("Проверить")
        _ = try qaRequest("/mobile/qa-api-state", body: ["unavailable": false])
        tapButton("Повторить отправку")
        let synced = NSPredicate { _, _ in
            (try? self.qaRequest("/mobile/qa-api-state")["ios_offline_note_count"] as? Int) == 1
        }
        expectation(for: synced, evaluatedWith: nil)
        waitForExpectations(timeout: 25)
        app.terminate()
        app.launch()
        XCTAssertEqual(try qaRequest("/mobile/qa-api-state")["ios_offline_note_count"] as? Int, 1)
    }

    func test04LocalNotificationOpensDatesAfterTermination() throws {
        let auth = try qaRequest("/api/auth/email/start", body: ["email": "ios-qa@example.ru"])
        _ = try qaRequest("/api/auth/email/verify", body: ["email": "ios-qa@example.ru", "code": try XCTUnwrap(auth["debug_code"])])
        let pets = try qaRequest("/api/pets")
        let pet = try XCTUnwrap((pets["items"] as? [[String: Any]])?.first)
        let due = Date().addingTimeInterval(120)
        let day = DateFormatter(); day.dateFormat = "yyyy-MM-dd"; day.locale = Locale(identifier: "en_US_POSIX")
        let time = DateFormatter(); time.dateFormat = "HH:mm"; time.locale = Locale(identifier: "en_US_POSIX")
        _ = try qaRequest("/api/reminders", body: ["pet_id": try XCTUnwrap(pet["id"]), "reminder_type": "custom",
            "title": "QA iOS local reminder", "due_date": day.string(from: due), "due_time": time.string(from: due), "periodicity": "once"])
        tapButton("Профиль")
        tapButton("Включить уведомления")
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = app.alerts.buttons["Allow"]
        if allow.waitForExistence(timeout: 8) { allow.tap() }
        else if springboard.buttons["Allow"].exists { springboard.buttons["Allow"].tap() }
        tapButton("Даты")
        XCTAssertTrue(app.staticTexts["QA iOS local reminder"].waitForExistence(timeout: 15))
        XCUIDevice.shared.press(.home)
        app.terminate()
        let delivered = springboard.staticTexts["QA iOS local reminder"]
        XCTAssertTrue(delivered.waitForExistence(timeout: 150))
        delivered.tap()
        XCTAssertTrue(app.staticTexts["QA iOS local reminder"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["Отключить"].exists)
    }

    func test05DoctorSummaryExportsToSystemPDFSheet() {
        openPet()
        tapButtonBeginning("Сводка для врача")
        tapButton("Печать или сохранить в PDF")
        let save = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Save to Files")).firstMatch
        XCTAssertTrue(save.waitForExistence(timeout: 25))
        if app.buttons["Close"].exists { app.buttons["Close"].tap() }
        else { app.swipeDown() }
    }

    func test06PetPhotoIsSavedFromTheSystemPicker() throws {
        openPet()
        tapButton("Добавить фото")
        // WebKit localizes its file menu from the document language (Russian),
        // independently of the simulator's English system locale.
        let library = app.buttons.matching(NSPredicate(format: "label IN %@", ["Медиатека", "Photo Library"])).firstMatch
        XCTAssertTrue(library.waitForExistence(timeout: 10))
        library.tap()
        // The current system picker exposes photo thumbnails as Images, not
        // UICollectionView cells. Match their visible accessibility labels.
        let photo = app.images.matching(NSPredicate(format: "label BEGINSWITH %@ OR label BEGINSWITH %@",
                                                     "Photo,", "Фото,")).firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 25))
        photo.tap()
        let choose = app.buttons.matching(NSPredicate(format: "label IN %@", ["Choose", "Выбрать"])).firstMatch
        if choose.waitForExistence(timeout: 3) { choose.tap() }
        let add = app.buttons.matching(NSPredicate(format: "label IN %@", ["Add", "Добавить"])).firstMatch
        if add.exists { add.tap() }
        let saved = NSPredicate { _, _ in
            (try? self.qaRequest("/mobile/qa-api-state")["ios_photo_count"] as? Int) == 1
        }
        expectation(for: saved, evaluatedWith: nil)
        waitForExpectations(timeout: 25)
        XCTAssertTrue(app.buttons["Изменить фото"].exists)
        app.terminate()
        app.launch()
        openPet()
        XCTAssertTrue(app.buttons["Изменить фото"].exists)
    }

    func test07AnalysisCanWaitLongerThanFifteenSeconds() {
        openPet()
        tapButtonBeginning("Что изменилось?")
        let complaint = app.textViews["Что происходит?"]
        XCTAssertTrue(complaint.waitForExistence(timeout: 10))
        complaint.tap()
        complaint.typeText("QA_IOS_SLOW_RESPONSE_20261021: routine test only")
        let started = Date()
        tapButton("Получить и сохранить разбор")
        XCTAssertTrue(app.buttons["Рассказать ещё раз"].waitForExistence(timeout: 50))
        XCTAssertGreaterThan(Date().timeIntervalSince(started), 16)
        XCTAssertTrue(app.buttons["Скопировать для врача"].exists)
    }
}
