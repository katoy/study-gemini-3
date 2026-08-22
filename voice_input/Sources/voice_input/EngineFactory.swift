import Foundation

/// エンジンファクトリ：設定名からエンジンインスタンスを生成 (FR-5.1, FR-5.2)
public enum EngineFactory {
    /// エンジン生成エラー
    public enum FactoryError: LocalizedError {
        case unknownEngineName(String)

        public var errorDescription: String? {
            switch self {
            case .unknownEngineName(let name):
                return "不明なエンジン名: \(name)"
            }
        }
    }

    /// VAD エンジンファクトリ
    /// - Parameter engineName: エンジン名（"DummyVADEngine"等）
    /// - Returns: 指定されたエンジンのインスタンス
    /// - Throws: `FactoryError` が不明なエンジン名の場合
    public static func createVADEngine(from engineName: String) throws -> VADEngine {
        switch engineName {
        case "DummyVADEngine":
            return DummyVADEngine()
        default:
            throw FactoryError.unknownEngineName(engineName)
        }
    }

    /// ストリーミング ASR エンジンファクトリ
    public static func createStreamingASREngine(from engineName: String) throws -> StreamingASREngine {
        switch engineName {
        case "AppleSpeechAnalyzerEngine":
            return AppleSpeechAnalyzerEngine()
        default:
            throw FactoryError.unknownEngineName(engineName)
        }
    }

    /// バッチ ASR エンジンファクトリ
    public static func createBatchASREngine(from engineName: String) throws -> BatchASREngine {
        switch engineName {
        case "AppleSpeechAnalyzerEngine":
            return AppleSpeechAnalyzerEngine()
        default:
            throw FactoryError.unknownEngineName(engineName)
        }
    }

    /// Refiner（LLM 整形）エンジンファクトリ
    public static func createRefinerEngine(from engineName: String) throws -> RefinerEngine {
        switch engineName {
        case "RuleBasedRefinerEngine":
            return RuleBasedRefinerEngine()
        default:
            throw FactoryError.unknownEngineName(engineName)
        }
    }

    /// 設定に基づいてパイプラインを作成
    /// - Parameter config: アプリケーション設定
    /// - Parameter dictionaryManager: ユーザー辞書マネージャ
    /// - Returns: 設定に基づいて初期化されたパイプライン
    /// - Throws: 不明なエンジン名の場合
    public static func createPipeline(
        from config: AppConfig,
        dictionaryManager: UserDictionaryManager
    ) throws -> VoiceInputPipeline {
        let vad = try createVADEngine(from: config.engines.vad)
        let streaming = try createStreamingASREngine(from: config.engines.streamingASR)
        let batch = try createBatchASREngine(from: config.engines.batchASR)
        let refiner = try createRefinerEngine(from: config.engines.refiner)

        return VoiceInputPipeline(
            vadEngine: vad,
            streamingASR: streaming,
            batchASR: batch,
            refinerEngine: refiner,
            dictionaryManager: dictionaryManager
        )
    }
}
