import Foundation

/// 音声入力処理パイプライン (FR-2)
public final class VoiceInputPipeline: @unchecked Sendable {
    private let vadEngine: VADEngine
    private let streamingASR: StreamingASREngine
    private let batchASR: BatchASREngine
    private let refinerEngine: RefinerEngine
    private let validator: OutputValidator
    
    public var dictionaryManager: UserDictionaryManager
    
    public init(
        vadEngine: VADEngine = DummyVADEngine(),
        streamingASR: StreamingASREngine = AppleSpeechAnalyzerEngine(),
        batchASR: BatchASREngine = AppleSpeechAnalyzerEngine(),
        refinerEngine: RefinerEngine = RuleBasedRefinerEngine(),
        validator: OutputValidator = OutputValidator(),
        dictionaryManager: UserDictionaryManager = UserDictionaryManager()
    ) {
        self.vadEngine = vadEngine
        self.streamingASR = streamingASR
        self.batchASR = batchASR
        self.refinerEngine = refinerEngine
        self.validator = validator
        self.dictionaryManager = dictionaryManager
    }
    
    public func start() async throws {
        try await vadEngine.load()
        try await streamingASR.load()
        try await batchASR.load()
        try await refinerEngine.load()
        
        try await vadEngine.warmup()
    }
    
    /// 音声ストリームのチャンク処理 (プレビュー用)
    public func processStreamChunk(_ chunk: AudioChunk) async throws -> (status: VADStatus, preview: String?) {
        let status = try await vadEngine.process(audioChunk: chunk)
        var previewText: String? = nil
        
        if status == .speaking || status == .speechStarted {
            previewText = try await streamingASR.processStream(audioChunk: chunk)
        }
        
        return (status, previewText)
    }
    
    /// 音声終了確定後の転写 & 整形処理
    public func processAudio(
        audioData: Data,
        sampleRate: Double,
        appCategory: String? = nil,
        strength: RefinerContext.RefinementStrength = .standard
    ) async throws -> String {
        // 1. バッチASR転写 (FR-2.3)
        let rawText: String
        do {
            rawText = try await batchASR.transcribe(audioData: audioData, sampleRate: sampleRate)
        } catch {
            print("Batch ASR failed: \(error)")
            throw error
        }
        
        // 2. 出力検証 (FR-2.4 - 空文字・ループ検知・言語判定)
        let validationResult = validator.validate(text: rawText)
        switch validationResult {
        case .empty:
            return ""
        case .repetitiveLoop(let pattern):
            print("Warning: Repetitive loop detected (pattern: '\(pattern)'). Suppressing output.")
            return ""
        case .languageMismatch(let detectedLanguage):
            print("Warning: Language mismatch detected (\(detectedLanguage)). Suppressing output.")
            return ""
        case .valid:
            break
        }
        
        // 3. LLM整形層 (FR-2.5, FR-3)
        let context = RefinerContext(
            dictionary: dictionaryManager.activeDictionary(),
            appCategory: appCategory,
            strength: strength
        )
        
        do {
            let refinedText = try await refinerEngine.refine(text: rawText, context: context)
            return refinedText
        } catch {
            // LLM整形が失敗・タイムアウトした場合は ASR生出力にフォールバック (FR-2.6)
            print("Refiner Engine failed (\(error.localizedDescription)). Falling back to raw text.")
            return rawText
        }
    }
}

