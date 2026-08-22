import Foundation
import AppKit
import Carbon

/// グローバルホットキー登録エラー
public enum HotKeyError: LocalizedError {
    case accessibilityPermissionDenied
    case failedToCreateEventTap

    public var errorDescription: String? {
        switch self {
        case .accessibilityPermissionDenied:
            return "Accessibility 権限がありません。システム設定で許可してください。"
        case .failedToCreateEventTap:
            return "グローバルホットキーの登録に失敗しました。"
        }
    }
}

public final class GlobalHotKeyManager: @unchecked Sendable {
    public enum HotKeyMode: String, Codable {
        case pushToTalk = "pushToTalk"  // キー押下中のみ録音
        case toggle = "toggle"  // 押下でON/OFF切り替え
    }

    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private let onHotKeyPressed: () -> Void
    private let onHotKeyReleased: () -> Void
    private var hotKeyMode: HotKeyMode

    /// ホットキー管理初期化 (FR-1.1)
    /// - Parameters:
    ///   - onHotKeyPressed: キー押下時のコールバック
    ///   - onHotKeyReleased: キー解放時のコールバック（Push-to-Talk モード用）
    ///   - mode: ホットキーモード（Push-to-Talk またはトグル）
    public init(
        onHotKeyPressed: @escaping () -> Void,
        onHotKeyReleased: @escaping () -> Void = {},
        mode: HotKeyMode = .toggle
    ) {
        self.onHotKeyPressed = onHotKeyPressed
        self.onHotKeyReleased = onHotKeyReleased
        self.hotKeyMode = mode
    }

    /// グローバルホットキー（Option + Space）を登録 (FR-1.1)
    /// - Throws: `HotKeyError` に基づいてエラーを伝播
    public func registerHotKey() throws {
        // Option + Space (keyCode: 49)
        // keyDown と keyUp の両方のイベントをキャッチ（Push-to-Talk 対応）
        let eventMask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue)

        let callback: CGEventTapCallBack = { proxy, type, event, refcon in
            let flags = event.flags
            let keyCode = event.getIntegerValueField(.keyboardEventKeycode)

            // Option key (.maskAlternate) + Space (49)
            guard flags.contains(.maskAlternate) && keyCode == 49 else {
                return Unmanaged.passRetained(event)
            }

            guard let refcon = refcon else {
                return Unmanaged.passRetained(event)
            }

            let manager = Unmanaged<GlobalHotKeyManager>.fromOpaque(refcon).takeUnretainedValue()

            if type == .keyDown {
                DispatchQueue.main.async {
                    manager.onHotKeyPressed()
                }
            } else if type == .keyUp {
                // Push-to-Talk モード時のみキー解放を処理
                if manager.hotKeyMode == .pushToTalk {
                    DispatchQueue.main.async {
                        manager.onHotKeyReleased()
                    }
                }
            }

            return nil  // イベントを消費
        }

        let selfPointer = Unmanaged.passUnretained(self).toOpaque()
        guard let tap = CGEvent.tapCreate(
            tap: .cghidEventTap,
            place: .headInsertEventTap,
            options: .defaultTap,
            eventsOfInterest: CGEventMask(eventMask),
            callback: callback,
            userInfo: selfPointer
        ) else {
            throw HotKeyError.accessibilityPermissionDenied
        }
        
        self.eventTap = tap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        self.runLoopSource = source
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
    }
    
    deinit {
        if let tap = eventTap {
            CGEvent.tapEnable(tap: tap, enable: false)
        }
        if let source = runLoopSource {
            CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source, .commonModes)
        }
    }
}
