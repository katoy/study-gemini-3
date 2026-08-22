import AppKit
import Foundation

/// アプリケーションのフォーカス（アクティブなフロントアプリ）を管理・復元するコンポーネント。
public protocol FocusManaging: Sendable {
    /// 現在フロントにあるアプリケーションを取得
    func captureFrontmostApplication() -> NSRunningApplication?
    
    /// 対象のアプリケーションへフォーカスを復元
    func restoreFocus(to targetApp: NSRunningApplication?, sleepMicroseconds: useconds_t)
}

public extension FocusManaging {
    func restoreFocus(to targetApp: NSRunningApplication?) {
        restoreFocus(to: targetApp, sleepMicroseconds: 200_000)
    }
}

public final class FocusManager: FocusManaging, @unchecked Sendable {
    public init() {}
    
    public func captureFrontmostApplication() -> NSRunningApplication? {
        guard let frontApp = NSWorkspace.shared.frontmostApplication,
              frontApp.bundleIdentifier != Bundle.main.bundleIdentifier else {
            return nil
        }
        return frontApp
    }
    
    public func restoreFocus(to targetApp: NSRunningApplication?, sleepMicroseconds: useconds_t = 200_000) {
        guard let targetApp = targetApp else { return }
        if #available(macOS 14.0, *) {
            targetApp.activate()
        } else {
            targetApp.activate(options: .activateIgnoringOtherApps)
        }
        if sleepMicroseconds > 0 {
            usleep(sleepMicroseconds)
        }
    }
}
