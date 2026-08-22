import Foundation
import AppKit
import SwiftUI

/// 履歴アイテム（タイムスタンプ付き）(FR-4.3, FR-4.4)
public struct HistoryItem: Codable, Hashable, Identifiable {
    public let id: UUID
    public let text: String
    public let timestamp: Date

    public init(id: UUID = UUID(), text: String, timestamp: Date = Date()) {
        self.id = id
        self.text = text
        self.timestamp = timestamp
    }

    public func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    public static func == (lhs: HistoryItem, rhs: HistoryItem) -> Bool {
        lhs.id == rhs.id
    }
}

/// 音声入力アプリ全体の状態を管理する ObservableObject (FR-1, FR-4.3)
public final class AppState: ObservableObject, @unchecked Sendable {
    @Published public var isRecording = false
    @Published public var previewText = ""
    @Published public var lastTranscribedText = ""
    @Published public var statusMessage = "準備完了"
    @Published public var history: [HistoryItem] = []  // 転写テキスト履歴 (FR-4.3, FR-4.4)
    public var maxHistoryItems: Int = 500  // 最大保持件数 (FR-4.4)
    public var maxHistoryDays: Int = 30  // 保存期間（日数）(FR-4.4)
    
    public let pipeline: VoiceInputPipeline
    public let audioCapture: AudioCaptureManager
    public let inserter: TextInserter
    public let focusManager: FocusManaging
    public let dictionaryManager: UserDictionaryManager
    
    private var recordedAudioData = Data()
    private var currentSampleRate: Double = 16000.0
    private var targetApp: NSRunningApplication?
    
    public init(
        focusManager: FocusManaging = FocusManager(),
        dictionaryManager: UserDictionaryManager = UserDictionaryManager(),
        configFilePath: String? = nil
    ) {
        self.focusManager = focusManager
        self.dictionaryManager = dictionaryManager
        self.inserter = TextInserter(focusManager: focusManager)
        self.audioCapture = AudioCaptureManager()

        // 設定ファイルから AppConfig を読み込み、パイプラインを初期化 (FR-5.2)
        let config: AppConfig
        if let path = configFilePath {
            config = AppConfig.load(from: path)
        } else {
            config = .default
        }

        do {
            self.pipeline = try EngineFactory.createPipeline(from: config, dictionaryManager: dictionaryManager)
        } catch {
            // ファクトリエラーの場合はデフォルトパイプラインにフォールバック
            self.pipeline = VoiceInputPipeline(dictionaryManager: dictionaryManager)
        }

        Task {
            do {
                try await pipeline.start()
            } catch {
                DispatchQueue.main.async {
                    self.statusMessage = "エラー: パイプライン起動失敗 (\(error.localizedDescription))"
                }
            }
        }
    }
    
    public func toggleRecording() {
        if isRecording {
            stopRecording()
        } else {
            startRecording()
        }
    }
    
    public func startRecording() {
        guard !isRecording else { return }
        
        // アクティブアプリを特定 (フォーカス復元・テキスト挿入用)
        self.targetApp = focusManager.captureFrontmostApplication()
        
        isRecording = true
        statusMessage = "録音中..."
        previewText = ""
        recordedAudioData.removeAll()
        
        audioCapture.onAudioChunk = { [weak self] chunk in
            guard let self = self else { return }
            self.recordedAudioData.append(chunk.data)
            self.currentSampleRate = chunk.sampleRate
            
            // リアルタイムストリーミングプレビュー処理 (FR-2.2)
            Task {
                if let (_, preview) = try? await self.pipeline.processStreamChunk(chunk), let previewText = preview {
                    await MainActor.run {
                        self.previewText = previewText
                    }
                } else {
                    await MainActor.run {
                        self.previewText = "録音中... (\(self.recordedAudioData.count / 1024) KB)"
                    }
                }
            }
        }
        
        do {
            try audioCapture.startCapture()
        } catch {
            statusMessage = "録音開始エラー: \(error.localizedDescription)"
            isRecording = false
        }
    }
    
    public func stopRecording() {
        guard isRecording else { return }
        isRecording = false
        statusMessage = "テキスト処理中..."
        audioCapture.stopCapture()
        
        let audioData = recordedAudioData
        let sampleRate = currentSampleRate
        let target = targetApp
        
        Task {
            do {
                let text = try await pipeline.processAudio(audioData: audioData, sampleRate: sampleRate)
                await MainActor.run {
                    self.lastTranscribedText = text
                    self.previewText = text
                    
                    if !text.isEmpty {
                        // 履歴に追加（タイムスタンプ付き）(FR-4.3, FR-4.4)
                        self.history.insert(HistoryItem(text: text), at: 0)
                        // 自動クリーンアップ（最大件数・保存期間）(FR-4.4)
                        self.cleanupHistory()
                        self.statusMessage = "テキスト挿入完了"
                        // カーソル位置への自動挿入 (FR-4.1)
                        self.inserter.insertText(text, targetApp: target)
                    } else {
                        self.statusMessage = "発話が検出されませんでした"
                        self.inserter.restoreFocus(targetApp: target)
                    }
                }
            } catch {
                await MainActor.run {
                    self.statusMessage = "エラー: \(error.localizedDescription)"
                    self.inserter.restoreFocus(targetApp: target)
                }
            }
        }
    }
    
    /// 履歴を一括クリアする (FR-4.4)
    public func clearHistory() {
        history.removeAll()
    }

    /// 履歴の自動クリーンアップ：最大件数・保存期間で管理 (FR-4.4)
    private func cleanupHistory() {
        // 1. 最大保持件数を超えたら古い順に削除（FIFO）
        if history.count > maxHistoryItems {
            history.removeSubrange(maxHistoryItems..<history.count)
        }

        // 2. 保存期間を超えたアイテムを削除
        let cutoffDate = Date().addingTimeInterval(-Double(maxHistoryDays) * 24 * 3600)
        history.removeAll { $0.timestamp < cutoffDate }
    }
}

