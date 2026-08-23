use arboard::Clipboard;
#[cfg(not(target_os = "macos"))]
use enigo::{Direction, Enigo, Key, Keyboard, Settings};
use tracing::{error, info};

#[cfg(target_os = "macos")]
pub mod macos_focus {
    use objc2::msg_send;
    use objc2::runtime::NSObject;
    use objc2_app_kit::NSRunningApplication;


    /// 現在アクティブ（最前面）なアプリケーションの Process Identifier (PID) を取得
    pub fn capture_frontmost_app_pid() -> Option<i32> {
        unsafe {
            let workspace_class = objc2::class!(NSWorkspace);
            let workspace: *mut NSObject = msg_send![workspace_class, sharedWorkspace];
            if workspace.is_null() {
                return None;
            }
            let front_app: *mut NSRunningApplication = msg_send![workspace, frontmostApplication];
            if front_app.is_null() {
                return None;
            }
            let pid: i32 = msg_send![front_app, processIdentifier];
            if pid != std::process::id() as i32 {
                Some(pid)
            } else {
                None
            }
        }
    }

    /// 指定した PID のアプリケーションへフォーカスをアクティブ化・復元
    pub fn restore_focus(pid: i32) {
        unsafe {
            let app_class = objc2::class!(NSRunningApplication);
            let app: *mut NSRunningApplication =
                msg_send![app_class, runningApplicationWithProcessIdentifier: pid];
            if !app.is_null() {
                // activate (macOS 14+) または activateWithOptions: (旧バージョン)
                // NSApplicationActivateIgnoringOtherApps = 1 << 0 (1u64)
                let success: bool = msg_send![app, activateWithOptions: 1u64];
                tracing::info!("Restored focus to PID {}: success={}", pid, success);
            } else {
                tracing::warn!("Could not find running application for PID {}", pid);
            }
        }
    }
}


pub struct TextInserter;

impl TextInserter {
    /// 対象のアプリケーションへフォーカスを復元する
    pub fn restore_focus(target_pid: Option<i32>) {
        #[cfg(target_os = "macos")]
        {
            if let Some(pid) = target_pid {
                info!("Restoring focus to target PID: {}", pid);
                macos_focus::restore_focus(pid);
                std::thread::sleep(std::time::Duration::from_millis(200));
            } else {
                info!("No target PID stored; skipping focus restoration.");
            }
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = target_pid;
        }
    }

    pub fn copy_and_paste(text: &str, target_pid: Option<i32>) -> anyhow::Result<()> {
        if text.is_empty() {
            return Ok(());
        }

        let mut clipboard = Clipboard::new()?;
        let previous = clipboard.get_text().ok();

        clipboard.set_text(text)?;
        info!("Text copied to clipboard: '{}'", text);

        if let Some(prev) = previous {
            info!("Previous clipboard contained {} chars", prev.len());
        }

        // 1. フォーカスを元のアプリへ復元
        Self::restore_focus(target_pid);

        // 2. 自動貼り付け (macOS では CGEvent を使用して確実に Cmd+V を送信)
        #[cfg(target_os = "macos")]
        {
            Self::paste_macos();
        }

        #[cfg(not(target_os = "macos"))]
        {
            match Enigo::new(&Settings::default()) {
                Ok(mut enigo) => {
                    let modifier = Key::Control;
                    std::thread::sleep(std::time::Duration::from_millis(200));
                    let _ = enigo.key(modifier, Direction::Press);
                    std::thread::sleep(std::time::Duration::from_millis(50));
                    let _ = enigo.key(Key::Unicode('v'), Direction::Click);
                    std::thread::sleep(std::time::Duration::from_millis(50));
                    let _ = enigo.key(modifier, Direction::Release);
                    info!("Pasted text via key simulation");
                }
                Err(e) => {
                    error!("Failed to initialize Enigo for pasting: {:?}", e);
                }
            }
        }

        Ok(())
    }

    #[cfg(target_os = "macos")]
    fn paste_macos() {
        // フォーカス遷移が完了するまで待機 (300ms)
        std::thread::sleep(std::time::Duration::from_millis(300));

        let status = std::process::Command::new("osascript")
            .arg("-e")
            .arg("tell application \"System Events\" to keystroke \"v\" using command down")
            .status();

        match status {
            Ok(s) if s.success() => info!("Pasted text via osascript (Cmd+V)"),
            _ => error!("Failed to paste text via osascript"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_copy_and_paste() {
        let res = TextInserter::copy_and_paste("hello world", None);
        if let Ok(()) = res {
            if let Ok(mut cb) = Clipboard::new() {
                assert_eq!(cb.get_text().ok(), Some("hello world".to_string()));
            }
        }
    }

    #[test]
    fn test_copy_and_paste_empty() {
        assert!(TextInserter::copy_and_paste("", None).is_ok());
    }

    #[test]
    fn test_restore_focus_none() {
        TextInserter::restore_focus(None);
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn test_macos_focus_functions() {
        let _pid = macos_focus::capture_frontmost_app_pid();
        macos_focus::restore_focus(999999);
    }
}

