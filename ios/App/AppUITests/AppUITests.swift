import XCTest

final class AppUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "ru.temichevvet.app.qa")

    override func setUpWithError() throws {
        continueAfterFailure = false
        app.launch()
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
        for _ in 0..<4 {
            if let button = buttons.allElementsBoundByIndex.first(where: { $0.isHittable }) {
                button.tap()
                return
            }
            app.swipeUp()
        }
        XCTFail("Button is not reachable: " + label, file: file, line: line)
    }

    func test01GuestShell() {
        XCTAssertTrue(app.staticTexts["Всё важное о питомце"].waitForExistence(timeout: 25))
        for label in ["Главная", "Питомцы", "Здоровье", "Даты", "Ещё"] {
            XCTAssertTrue(app.buttons[label].exists, "Missing app tab: " + label)
        }
        XCTAssertTrue(app.buttons["Войти или создать аккаунт"].exists)
    }

    func test02EmailLoginAndTabs() throws {
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
        for label in ["Питомцы", "Здоровье", "Даты", "Ещё", "Главная"] {
            tapButton(label)
            XCTAssertTrue(app.buttons["Главная"].exists)
        }
    }
}
