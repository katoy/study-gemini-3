import Foundation

/// キャプチャされた音声データチャンク
public struct AudioChunk: Sendable {
    public let data: Data
    public let sampleRate: Double
    public let channels: Int
    
    public init(data: Data, sampleRate: Double = 16000.0, channels: Int = 1) {
        self.data = data
        self.sampleRate = sampleRate
        self.channels = channels
    }
}

/// VAD (音声区間検出) のステータス
public enum VADStatus: Equatable, Sendable {
    case silence
    case speechStarted
    case speaking
    case speechEnded
}

/// VAD エンジンプロトコル (FR-5.1)
public protocol VADEngine: Sendable {
    func load() async throws
    func unload() async throws
    func warmup() async throws
    func process(audioChunk: AudioChunk) async throws -> VADStatus
}

public extension VADEngine {
    func warmup() async throws {}
}

/// ストリーミング ASR エンジンプロトコル (FR-5.1)
public protocol StreamingASREngine: Sendable {
    func load() async throws
    func unload() async throws
    func processStream(audioChunk: AudioChunk) async throws -> String
    func resetStream() async throws
}

/// バッチ ASR エンジンプロトコル (FR-5.1)
public protocol BatchASREngine: Sendable {
    func load() async throws
    func unload() async throws
    func transcribe(audioData: Data, sampleRate: Double) async throws -> String
}

/// LLM整形層コンテキスト情報 (FR-3)
public struct RefinerContext: Sendable {
    public let dictionary: [String: String]
    public let appCategory: String?
    public let strength: RefinementStrength
    public let customInstruction: String?
    
    public enum RefinementStrength: String, Codable, Sendable, CaseIterable {
        case none
        case light
        case standard
        case aggressive
    }
    
    public init(
        dictionary: [String: String] = [:],
        appCategory: String? = nil,
        strength: RefinementStrength = .standard,
        customInstruction: String? = nil
    ) {
        self.dictionary = dictionary
        self.appCategory = appCategory
        self.strength = strength
        self.customInstruction = customInstruction
    }
}

/// Refiner (LLM整形) エンジンプロトコル (FR-5.1)
public protocol RefinerEngine: Sendable {
    func load() async throws
    func unload() async throws
    func refine(text: String, context: RefinerContext) async throws -> String
}

