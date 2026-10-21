import Capacitor
import UIKit
import WebKit

private final class VetPrintRenderer: UIPrintPageRenderer {
    override var paperRect: CGRect { CGRect(x: 0, y: 0, width: 595.28, height: 841.89) }
    override var printableRect: CGRect { paperRect.insetBy(dx: 32, dy: 32) }
}

@objc(NativeDocumentsPlugin)
public class NativeDocumentsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "NativeDocumentsPlugin"
    public let jsName = "NativeDocuments"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "print", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openExternal", returnType: CAPPluginReturnPromise)
    ]
    private var sharing = false

    @objc func openExternal(_ call: CAPPluginCall) {
        guard let value = call.getString("url"), let url = URL(string: value),
              ["tel", "mailto"].contains(url.scheme?.lowercased() ?? "") else {
            call.reject("invalid_external_url")
            return
        }
        DispatchQueue.main.async {
            UIApplication.shared.open(url, options: [:]) { opened in
                if opened { call.resolve() } else { call.reject("external_app_unavailable") }
            }
        }
    }

    @objc func print(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard !self.sharing, let webView = self.bridge?.webView,
                  let presenter = self.bridge?.viewController,
                  presenter.presentedViewController == nil else {
                call.reject("document_view_unavailable")
                return
            }
            self.sharing = true
            let renderer = VetPrintRenderer()
            renderer.addPrintFormatter(webView.viewPrintFormatter(), startingAtPageAt: 0)
            let pages = renderer.numberOfPages
            guard pages > 0, pages <= 500 else {
                self.sharing = false
                call.reject("document_has_no_printable_pages")
                return
            }
            renderer.prepare(forDrawingPages: NSRange(location: 0, length: pages))
            let pdf = UIGraphicsPDFRenderer(bounds: renderer.paperRect)
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("TemichevVet-\(UUID().uuidString).pdf")
            do {
                try pdf.writePDF(to: file) { context in
                    for page in 0..<pages {
                        context.beginPage()
                        renderer.drawPage(at: page, in: context.pdfContextBounds)
                    }
                }
                let activity = UIActivityViewController(activityItems: [file], applicationActivities: nil)
                if let popover = activity.popoverPresentationController {
                    popover.sourceView = presenter.view
                    popover.sourceRect = CGRect(x: presenter.view.bounds.midX,
                                                y: presenter.view.bounds.midY, width: 0, height: 0)
                    popover.permittedArrowDirections = []
                }
                activity.completionWithItemsHandler = { _, completed, _, error in
                    self.sharing = false
                    try? FileManager.default.removeItem(at: file)
                    if let error = error { call.reject("document_share_failed", nil, error) }
                    else { call.resolve(["completed": completed]) }
                }
                presenter.present(activity, animated: true)
            } catch {
                self.sharing = false
                try? FileManager.default.removeItem(at: file)
                call.reject("document_export_failed", nil, error)
            }
        }
    }
}
