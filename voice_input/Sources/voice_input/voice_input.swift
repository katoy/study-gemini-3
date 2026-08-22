import AppKit
import SwiftUI

@main
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private let appState = AppState()
    private var hotKeyManager: GlobalHotKeyManager?
    
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.run()
    }
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // メニューバー常駐設定 (FR-1.2)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "🎙️ VoiceInput"
            button.action = #selector(togglePopover)
            button.target = self
        }
        
        // フローティング HUD Popover 設定 (FR-1.3)
        popover = NSPopover()
        popover.contentSize = NSSize(width: 340, height: 220)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(rootView: HUDView(appState: appState))
        
        // グローバルショートカット (Option + Space) の登録 (FR-1.1)
        hotKeyManager = GlobalHotKeyManager { [weak self] in
            self?.appState.toggleRecording()
        }
        hotKeyManager?.registerHotKey()
        
        // パイプライン初期化
        Task {
            try? await appState.pipeline.start()
        }
    }
    
    @objc private func togglePopover() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(nil)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            if let window = popover.contentViewController?.view.window {
                window.styleMask.insert(.nonactivatingPanel)
                window.level = .floating
                window.canHide = false
                if let panel = window as? NSPanel {
                    panel.becomesKeyOnlyIfNeeded = true
                }
            }
        }
    }
}

