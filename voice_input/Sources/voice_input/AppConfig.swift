import Foundation

/// アプリケーション設定：エンジン選択・カスタマイズ (FR-5.2)
public struct AppConfig: Codable, Sendable {
    /// 使用するエンジンの組み合わせ（設定で宣言的に選択）
    public let engines: EngineConfiguration

    /// デフォルト設定（全エンジン実装利用）
    public static let `default` = AppConfig(
        engines: EngineConfiguration(
            vad: "DummyVADEngine",
            streamingASR: "AppleSpeechAnalyzerEngine",
            batchASR: "AppleSpeechAnalyzerEngine",
            refiner: "RuleBasedRefinerEngine"
        )
    )

    /// 設定ファイルから読み込む
    /// - Parameter filePath: 設定ファイルのパス
    /// - Returns: 読み込んだ AppConfig インスタンス（失敗時はデフォルト）
    public static func load(from filePath: String) -> AppConfig {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: filePath)) else {
            return .default
        }

        let decoder = JSONDecoder()
        if let config = try? decoder.decode(AppConfig.self, from: data) {
            return config
        }

        return .default
    }

    /// エンジン設定セクション
    public struct EngineConfiguration: Codable, Sendable {
        /// VAD エンジンの選択
        public let vad: String

        /// ストリーミング ASR エンジンの選択
        public let streamingASR: String

        /// バッチ ASR エンジンの選択
        public let batchASR: String

        /// LLM 整形（Refiner）エンジンの選択
        public let refiner: String

        public init(vad: String, streamingASR: String, batchASR: String, refiner: String) {
            self.vad = vad
            self.streamingASR = streamingASR
            self.batchASR = batchASR
            self.refiner = refiner
        }

        enum CodingKeys: String, CodingKey {
            case vad = "vad"
            case streamingASR = "streamingASR"
            case batchASR = "batchASR"
            case refiner = "refiner"
        }
    }
}
