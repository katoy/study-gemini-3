import Foundation
import AppKit

/// テキスト挿入・クリップボード操作マネージャ (FR-4)
public final class TextInserter: @unchecked Sendable {
    private let focusManager: FocusManaging
    
    public init(focusManager: FocusManaging = FocusManager()) {
        self.focusManager = focusManager
    }
    
    public func restoreFocus(targetApp: NSRunningApplication?) {
        focusManager.restoreFocus(to: targetApp)
    }
    
    /// カーソル位置へのテキスト自動挿入 (FR-4.1, FR-4.2)
    public func insertText(_ text: String, targetApp: NSRunningApplication? = nil) {
        restoreFocus(targetApp: targetApp)
        
        guard !text.isEmpty else { return }
        
        let pasteboard = NSPasteboard.general
        let oldString = pasteboard.string(forType: .string)
        
        // クリップボード退避＆新テキストセット
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
        
        // Command + V キーイベントを送信して貼り付け
        simulatePaste()
        
        // 挿入後に元のクリップボード内容を復元 (FR-4.2)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            if let old = oldString {
                pasteboard.clearContents()
                pasteboard.setString(old, forType: .string)
            }
        }
    }
    
    /// Cmd+V の合成キーイベント送信
    private func simulatePaste() {
        let source = CGEventSource(stateID: .combinedSessionState)
        let vKeyCode: CGKeyCode = 0x09 // 'v'
        
        guard let keyDown = CGEvent(keyboardEventSource: source, virtualKey: vKeyCode, keyDown: true),
              let keyUp = CGEvent(keyboardEventSource: source, virtualKey: vKeyCode, keyDown: false) else {
            return
        }
        
        keyDown.flags = .maskCommand
        keyUp.flags = .maskCommand
        
        keyDown.post(tap: .cghidEventTap)
        keyUp.post(tap: .cghidEventTap)
    }
}


