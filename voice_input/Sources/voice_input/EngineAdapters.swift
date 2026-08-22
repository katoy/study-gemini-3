import Foundation
import Speech
import AVFoundation

// MARK: - エラーコード定義（マジックナンバーを定数化）
private enum AppleSpeechAnalyzerErrorCode: Int {
    case authorizationFailed = 1
    case recognizerUnavailable = 2
    case audioFormatFailed = 3
    case pcmBufferCreationFailed = 4
}

// MARK: - LLM整形用フィラー辞書（定数化）
private let FILLER_WORDS = [
    "えーと", "あのー", "そのー", "その", "ねえ",
    "まあ", "ほら", "つまり", "いわば", "ともかく",
    "ところで", "それにしても"
]

// MARK: - 言い直し・自己修正解決用正規表現パターン
private let CORRECTION_PATTERN = "(.+)じゃなくて(.+)"

// MARK: - Dummy VAD Engine (エネルギー検出型フォールバック)
public final class DummyVADEngine: VADEngine, @unchecked Sendable {
    private var energyThreshold: Float
    
    public init(energyThreshold: Float = 0.01) {
        self.energyThreshold = energyThreshold
    }
    
    public func load() async throws {}
    public func unload() async throws {}
    public func warmup() async throws {}
    
    public func process(audioChunk: AudioChunk) async throws -> VADStatus {
        let count = audioChunk.data.count / MemoryLayout<Int16>.stride
        guard count > 0 else { return .silence }
        
        var sum: Float = 0
        audioChunk.data.withUnsafeBytes { (buffer: UnsafeRawBufferPointer) in
            let samples = buffer.bindMemory(to: Int16.self)
            for sample in samples {
                let norm = Float(sample) / 32768.0
                sum += norm * norm
            }
        }
        let rms = sqrt(sum / Float(count))
        return rms > energyThreshold ? .speaking : .silence
    }
}

// MARK: - Apple Speech Framework ASR Engine Adapter
public final class AppleSpeechAnalyzerEngine: BatchASREngine, StreamingASREngine, @unchecked Sendable {
    private let locale: Locale
    private var streamBuffer: Data = Data()
    private var lastStreamingResult: String = ""

    public init(locale: Locale = Locale(identifier: "ja-JP")) {
        self.locale = locale
    }
    
    public func load() async throws {
        await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { _ in
                continuation.resume()
            }
        }
    }
    
    public func unload() async throws {}
    
    public func transcribe(audioData: Data, sampleRate: Double) async throws -> String {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            throw NSError(domain: "AppleSpeechAnalyzerEngine", code: AppleSpeechAnalyzerErrorCode.authorizationFailed.rawValue, userInfo: [
                NSLocalizedDescriptionKey: "音声認識の権限がありません。"
            ])
        }

        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            throw NSError(domain: "AppleSpeechAnalyzerEngine", code: AppleSpeechAnalyzerErrorCode.recognizerUnavailable.rawValue, userInfo: [
                NSLocalizedDescriptionKey: "SFSpeechRecognizer が利用できません。"
            ])
        }

        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: false) else {
            throw NSError(domain: "AppleSpeechAnalyzerEngine", code: AppleSpeechAnalyzerErrorCode.audioFormatFailed.rawValue, userInfo: [
                NSLocalizedDescriptionKey: "AVAudioFormat 作成に失敗しました。"
            ])
        }

        let frameCount = UInt32(audioData.count) / format.streamDescription.pointee.mBytesPerFrame
        guard frameCount > 0 else { return "" }

        guard let pcmBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else {
            throw NSError(domain: "AppleSpeechAnalyzerEngine", code: AppleSpeechAnalyzerErrorCode.pcmBufferCreationFailed.rawValue, userInfo: [
                NSLocalizedDescriptionKey: "AVAudioPCMBuffer 作成に失敗しました。"
            ])
        }
        pcmBuffer.frameLength = frameCount
        
        audioData.withUnsafeBytes { (rawBuffer: UnsafeRawBufferPointer) in
            if let baseAddress = rawBuffer.baseAddress, let channelData = pcmBuffer.int16ChannelData {
                channelData[0].initialize(from: baseAddress.assumingMemoryBound(to: Int16.self), count: Int(frameCount))
            }
        }
        
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = false
        request.append(pcmBuffer)
        request.endAudio()
        
        return try await withCheckedThrowingContinuation { continuation in
            var hasResumed = false
            recognizer.recognitionTask(with: request) { result, error in
                guard !hasResumed else { return }
                if let error = error {
                    hasResumed = true
                    continuation.resume(throwing: error)
                } else if let result = result, result.isFinal {
                    hasResumed = true
                    continuation.resume(returning: result.bestTranscription.formattedString)
                }
            }
        }
    }
    
    /// ストリーミング ASR プレビュー実装 (FR-2.2)
    /// 音声チャンクを蓄積し、一定量に達したら暫定テキストを返す（低遅延プレビュー）
    public func processStream(audioChunk: AudioChunk) async throws -> String {
        // 音声バッファに蓄積
        streamBuffer.append(audioChunk.data)

        // 蓄積量が 8KB 以上なら暫定認識を実施（レイテンシ削減）
        guard streamBuffer.count >= 8192 else {
            return lastStreamingResult  // 蓄積不足なら前回結果を返す
        }

        do {
            // 暫定テキストを取得
            let partialText = try await transcribePartial(audioData: streamBuffer, sampleRate: audioChunk.sampleRate)
            lastStreamingResult = partialText
            streamBuffer.removeAll()  // バッファをクリア
            return partialText
        } catch {
            // 認識失敗時は前回結果を返す
            return lastStreamingResult
        }
    }

    /// ストリーミングバッファをリセット
    public func resetStream() async throws {
        streamBuffer.removeAll()
        lastStreamingResult = ""
    }

    /// 部分音声の暫定認識（ストリーミング用補助メソッド）
    private func transcribePartial(audioData: Data, sampleRate: Double) async throws -> String {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            return lastStreamingResult
        }

        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            return lastStreamingResult
        }

        guard let format = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: 1, interleaved: false) else {
            return lastStreamingResult
        }

        let frameCount = UInt32(audioData.count) / format.streamDescription.pointee.mBytesPerFrame
        guard frameCount > 0 else { return lastStreamingResult }

        guard let pcmBuffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameCount) else {
            return lastStreamingResult
        }

        pcmBuffer.frameLength = frameCount
        audioData.withUnsafeBytes { (buffer: UnsafeRawBufferPointer) in
            guard let addr = buffer.baseAddress else { return }
            memcpy(pcmBuffer.int16ChannelData?[0], addr, audioData.count)
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.append(pcmBuffer)
        request.endAudio()

        return await withCheckedContinuation { continuation in
            recognizer.recognitionTask(with: request) { result, error in
                if let result = result {
                    continuation.resume(returning: result.bestTranscription.formattedString)
                } else {
                    continuation.resume(returning: "")
                }
            }
        }
    }
}

// MARK: - Rule-based LLM Refiner Engine
public final class RuleBasedRefinerEngine: RefinerEngine, @unchecked Sendable {
    public init() {}
    
    public func load() async throws {}
    public func unload() async throws {}
    
    /// LLM 整形層（段階的整形強度対応）(FR-3.1～3.7)
    public func refine(text: String, context: RefinerContext) async throws -> String {
        guard context.strength != .none else {
            return text  // 整形なし
        }

        var result = text

        // ===== Light: 句読点のみ =====
        if context.strength == .light {
            result = result.trimmingCharacters(in: .whitespacesAndNewlines)
            // 句読点付与
            if !result.isEmpty && !result.hasSuffix("。") && !result.hasSuffix("？") && !result.hasSuffix("！") {
                result += "。"
            }
            return result
        }

        // ===== Standard & Aggressive: 以下を実行 =====

        // 1. フィラー除去 (FR-3.1)
        for filler in FILLER_WORDS {
            result = result.replacingOccurrences(of: filler, with: "")
        }

        // 2. 言い直し・自己修正の解決 (FR-3.2)
        // 例: 「AAAじゃなくてBBB」→「BBB」
        if let regex = try? NSRegularExpression(pattern: CORRECTION_PATTERN, options: []) {
            let nsRange = NSRange(result.startIndex..<result.endIndex, in: result)
            result = regex.stringByReplacingMatches(in: result, options: [], range: nsRange, withTemplate: "$2")
        }

        // 3. ユーザー辞書適用 (FR-3.4 / FR-6.2)
        for (reading, target) in context.dictionary {
            result = result.replacingOccurrences(of: reading, with: target)
        }

        // 4. 余分な先頭・末尾空白の除去
        result = result.trimmingCharacters(in: .whitespacesAndNewlines)

        // 5. 文中の句点補完
        let sentenceEndPattern = "(ですね|です|ます|でした|ました)(?=[^。？！\\s])"
        result = result.replacingOccurrences(of: sentenceEndPattern, with: "$1。", options: .regularExpression)

        // 6. 句読点付与 (FR-3.3)
        if !result.isEmpty && !result.hasSuffix("。") && !result.hasSuffix("？") && !result.hasSuffix("！") {
            result += "。"
        }

        // ===== Aggressive のみ: 改行処理 =====
        if context.strength == .aggressive {
            // 簡易改行：句点毎に改行（最大 40 文字/行）
            result = addLineBreaks(to: result)
        }

        return result
    }

    /// 改行挿入の簡易実装（句点毎に区切り、最大 40 文字まで）(FR-3.3)
    private func addLineBreaks(to text: String) -> String {
        var result = ""
        var lineLength = 0
        let maxLineLength = 40

        for scalar in text.unicodeScalars {
            let char = Character(scalar)
            result.append(char)
            lineLength += 1

            // 句点で改行
            if ["。", "？", "！"].contains(String(char)) {
                result.append("\n")
                lineLength = 0
            }
            // 最大行長を超えたら改行
            else if lineLength >= maxLineLength && scalar.value == 0x20 {  // スペース
                result.append("\n")
                lineLength = 0
            }
        }

        return result
    }
}

