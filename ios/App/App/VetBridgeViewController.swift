import Capacitor
import UIKit

class VetBridgeViewController: CAPBridgeViewController {
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(NativeDocumentsPlugin())
        bridge?.registerPluginInstance(NativeRemindersPlugin())
        webView?.scrollView.contentInsetAdjustmentBehavior = .never
        view.backgroundColor = UIColor(red: 244 / 255, green: 247 / 255, blue: 251 / 255, alpha: 1)
    }
}
