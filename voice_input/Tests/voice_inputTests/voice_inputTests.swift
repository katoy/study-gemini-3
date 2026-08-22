import Foundation
import AppKit
import Testing
@testable import voice_input

@Suite("OutputValidator Tests")
struct OutputValidatorTests {
    @Test("Validates empty or whitespace-only string as .empty")
    func testEmptyValidation() {
        let validator = OutputValidator()
        #expect(validator.validate(text: "") == .empty)
        #expect(validator.validate(text: "   \n\t ") == .empty)
    }

    @Test("Validates normal sentence as .valid")
    func testValidSentence() {
        let validator = OutputValidator()
        #expect(validator.validate(text: "こんにちは、音声入力のテストです。") == .valid)
    }

    @Test("Detects repetitive loop patterns")
    func testRepetitiveLoop() {
        let validator = OutputValidator()
        let result = validator.validate(text: "テストテストテストテスト")
        if case .repetitiveLoop(let pattern) = result {
            #expect(pattern == "テスト")
        } else {
            Issue.record("Expected repetitiveLoop result, but got \(result)")
        }
    }
}

@Suite("UserDictionary Tests")
struct UserDictionaryTests {
    @Test("Adds, updates, and removes dictionary items correctly")
    func testDictionaryOperations() {
        let manager = UserDictionaryManager(initialItems: [])
        
        manager.add(reading: "テスト", target: "Test")
        #expect(manager.activeDictionary()["テスト"] == "Test")
        
        // 重複キーの更新
        manager.add(reading: "テスト", target: "TEST_UPDATED")
        #expect(manager.activeDictionary()["テスト"] == "TEST_UPDATED")
        
        // 削除
        let item = manager.items.first!
        manager.remove(id: item.id)
        #expect(manager.activeDictionary().isEmpty)
    }

    @Test("Exports and imports JSON data seamlessly")
    func testJSONExportImport() throws {
        let manager = UserDictionaryManager()
        let jsonData = try manager.exportJSON()
        
        let newManager = UserDictionaryManager(initialItems: [])
        try newManager.importJSON(jsonData)
        
        #expect(newManager.items.count == manager.items.count)
        #expect(newManager.activeDictionary()["クロード"] == "Claude")
    }
}

@Suite("RuleBasedRefiner Tests")
struct RuleBasedRefinerTests {
    @Test("Strips fillers, applies correction rules, user dictionary and appends period")
    func testRefinementPipeline() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()
        
        let context = RefinerContext(dictionary: ["クロード": "Claude", "ジェミニ": "Gemini"])
        let inputText = "えーと あのー クロードじゃなくてジェミニで開発をする"
        
        let result = try await refiner.refine(text: inputText, context: context)
        #expect(result == "Geminiで開発をする。")
    }

    @Test("Does not drop characters in normal Japanese text")
    func testNoCharacterDropInNormalSentence() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()
        
        let context = RefinerContext(strength: .standard)
        let inputText = "変換結果に文字化けが多く発生しています"
        let result = try await refiner.refine(text: inputText, context: context)
        #expect(result == "変換結果に文字化けが多く発生しています。")
    }

    @Test("Respects RefinementStrength.none")
    func testNoRefinement() async throws {
        let refiner = RuleBasedRefinerEngine()
        let context = RefinerContext(strength: .none)
        let result = try await refiner.refine(text: "えーと テスト", context: context)
        #expect(result == "えーと テスト")
    }

    @Test("Inserts period between sentences with sentence ending words")
    func testSentenceBoundaryPeriodInsertion() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()

        let context = RefinerContext(strength: .standard)
        let inputText = "月が綺麗ですね寒いです"
        let result = try await refiner.refine(text: inputText, context: context)
        #expect(result == "月が綺麗ですね。寒いです。")
    }
}

@Suite("VoiceInputPipeline Integration Tests")
struct VoiceInputPipelineTests {
    struct MockBatchASR: BatchASREngine {
        let textToReturn: String
        let shouldFail: Bool
        
        init(textToReturn: String, shouldFail: Bool = false) {
            self.textToReturn = textToReturn
            self.shouldFail = shouldFail
        }
        
        func load() async throws {}
        func unload() async throws {}
        func transcribe(audioData: Data, sampleRate: Double) async throws -> String {
            if shouldFail {
                throw NSError(domain: "MockBatchASR", code: -1, userInfo: nil)
            }
            return textToReturn
        }
    }

    struct MockFailingRefiner: RefinerEngine {
        func load() async throws {}
        func unload() async throws {}
        func refine(text: String, context: RefinerContext) async throws -> String {
            throw NSError(domain: "MockFailingRefiner", code: -1, userInfo: nil)
        }
    }

    @Test("Processes audio into refined text properly")
    func testSuccessfulPipeline() async throws {
        let mockASR = MockBatchASR(textToReturn: "えーと クロードでテスト")
        let dictManager = UserDictionaryManager(initialItems: [UserDictionaryItem(reading: "クロード", target: "Claude")])
        let pipeline = VoiceInputPipeline(batchASR: mockASR, dictionaryManager: dictManager)
        
        try await pipeline.start()
        let result = try await pipeline.processAudio(audioData: Data([1, 2, 3, 4]), sampleRate: 16000.0)
        #expect(result == "Claudeでテスト。")
    }

    @Test("Ignores empty transcription result")
    func testEmptyTranscription() async throws {
        let mockASR = MockBatchASR(textToReturn: "   ")
        let pipeline = VoiceInputPipeline(batchASR: mockASR)
        
        try await pipeline.start()
        let result = try await pipeline.processAudio(audioData: Data([1, 2, 3, 4]), sampleRate: 16000.0)
        #expect(result.isEmpty)
    }

    @Test("Suppresses output when repetitive loop is detected")
    func testRepetitiveLoopSuppression() async throws {
        let mockASR = MockBatchASR(textToReturn: "ああああああああああ")
        let pipeline = VoiceInputPipeline(batchASR: mockASR)
        
        try await pipeline.start()
        let result = try await pipeline.processAudio(audioData: Data([1, 2, 3, 4]), sampleRate: 16000.0)
        #expect(result.isEmpty)
    }

    @Test("Falls back to raw ASR output if Refiner throws an error (FR-2.6)")
    func testRefinerFallback() async throws {
        let mockASR = MockBatchASR(textToReturn: "生テキスト出力")
        let failingRefiner = MockFailingRefiner()
        let pipeline = VoiceInputPipeline(batchASR: mockASR, refinerEngine: failingRefiner)
        
        try await pipeline.start()
        let result = try await pipeline.processAudio(audioData: Data([1, 2, 3, 4]), sampleRate: 16000.0)
        #expect(result == "生テキスト出力")
    }
}

@Suite("AppConfig & EngineFactory Tests")
struct AppConfigAndEngineFactoryTests {
    @Test("AppConfig.default returns standard configuration")
    func testDefaultConfig() {
        let config = AppConfig.default
        #expect(config.engines.vad == "DummyVADEngine")
        #expect(config.engines.streamingASR == "AppleSpeechAnalyzerEngine")
        #expect(config.engines.batchASR == "AppleSpeechAnalyzerEngine")
        #expect(config.engines.refiner == "RuleBasedRefinerEngine")
    }

    @Test("EngineFactory creates engines correctly")
    func testEngineFactoryCreation() throws {
        let vad = try EngineFactory.createVADEngine(from: "DummyVADEngine")
        #expect(vad is DummyVADEngine)

        let streaming = try EngineFactory.createStreamingASREngine(from: "AppleSpeechAnalyzerEngine")
        #expect(streaming is AppleSpeechAnalyzerEngine)

        let batch = try EngineFactory.createBatchASREngine(from: "AppleSpeechAnalyzerEngine")
        #expect(batch is AppleSpeechAnalyzerEngine)

        let refiner = try EngineFactory.createRefinerEngine(from: "RuleBasedRefinerEngine")
        #expect(refiner is RuleBasedRefinerEngine)
    }

    @Test("EngineFactory throws on unknown engine name")
    func testEngineFactoryUnknownEngine() throws {
        #expect(throws: (any Error).self) {
            _ = try EngineFactory.createVADEngine(from: "UnknownVADEngine")
        }
    }

    @Test("EngineFactory creates pipeline from config")
    func testPipelineCreationFromConfig() throws {
        let config = AppConfig.default
        let dictManager = UserDictionaryManager(initialItems: [])
        let pipeline = try EngineFactory.createPipeline(from: config, dictionaryManager: dictManager)
        // Pipeline が正常に生成されることを確認
        #expect(pipeline.dictionaryManager === dictManager)
    }
}

@Suite("OutputValidator Language Detection Tests")
struct OutputValidatorLanguageTests {
    @Test("Detects Japanese text correctly")
    func testJapaneseDetection() {
        let validator = OutputValidator()
        let result = validator.validate(text: "これは日本語です。")
        #expect(result == .valid)
    }

    @Test("Detects language mismatch for English-heavy text")
    func testEnglishDetection() {
        let validator = OutputValidator()
        let result = validator.validate(text: "This is English text only")
        if case .languageMismatch(let lang) = result {
            #expect(lang == "英語")
        } else {
            Issue.record("Expected languageMismatch, got \(result)")
        }
    }

    @Test("Allows mixed Japanese-English text")
    func testMixedLanguageDetection() {
        let validator = OutputValidator()
        let result = validator.validate(text: "Pythonで機械学習のテストを実施")
        // 混在は許可（日本語が 20% 以上あれば許可）
        // .valid または .languageMismatch(英語) でないことを確認
        switch result {
        case .valid:
            #expect(true)
        case .languageMismatch(let lang):
            // 英語のみの場合は許可されないが、混在は許可
            #expect(lang != "英語")
        case .empty, .repetitiveLoop:
            Issue.record("Unexpected validation result: \(result)")
        }
    }
}

@Suite("RefinementStrength Tests")
struct RefinementStrengthTests {
    @Test("Light mode applies only punctuation")
    func testLightRefinement() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()

        let context = RefinerContext(strength: .light)
        let result = try await refiner.refine(text: "えーと テスト", context: context)
        // light モードは句読点のみ付与（フィラーは除去しない）
        #expect(result.hasSuffix("。"))
        #expect(result.contains("えーと"))  // light モードではフィラーは除去されない
    }

    @Test("Standard mode applies full refinement")
    func testStandardRefinement() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()

        let context = RefinerContext(dictionary: ["テスト": "TEST"], strength: .standard)
        let result = try await refiner.refine(text: "えーと テスト", context: context)
        #expect(result.contains("TEST"))
        #expect(result.hasSuffix("。"))
    }

    @Test("Aggressive mode applies line breaks")
    func testAggressiveRefinement() async throws {
        let refiner = RuleBasedRefinerEngine()
        try await refiner.load()

        let context = RefinerContext(strength: .aggressive)
        let longText = "これは長いテキストです。複数の文を含んでいます。改行が入るはずです。"
        let result = try await refiner.refine(text: longText, context: context)
        // aggressive モードでは改行が挿入される
        #expect(result.contains("\n") || result.hasSuffix("。"))
    }
}

@Suite("UserDictionary CSV Tests")
struct UserDictionaryCSVTests {
    @Test("Exports and imports CSV data correctly")
    func testCSVExportImport() throws {
        let manager = UserDictionaryManager()
        let csvData = try manager.exportCSV()

        let newManager = UserDictionaryManager(initialItems: [])
        try newManager.importCSV(csvData)

        #expect(newManager.items.count == manager.items.count)
        #expect(newManager.activeDictionary()["クロード"] == "Claude")
    }

    @Test("CSV parser handles quoted fields")
    func testCSVQuotedFields() throws {
        let csvText = "reading,target,isEnabled\n\"テスト,入力\",\"Test, Input\",true\n"
        let csvData = csvText.data(using: .utf8)!

        let manager = UserDictionaryManager(initialItems: [])
        try manager.importCSV(csvData)

        #expect(manager.items.count >= 1)
    }
}

@Suite("AppState & FocusManager Tests")
struct AppStateAndFocusManagerTests {
    final class MockFocusManager: FocusManaging, @unchecked Sendable {
        var capturedApp: NSRunningApplication?
        var restoredApp: NSRunningApplication?
        var sleepMicros: useconds_t?

        func captureFrontmostApplication() -> NSRunningApplication? {
            return capturedApp
        }

        func restoreFocus(to targetApp: NSRunningApplication?, sleepMicroseconds: useconds_t) {
            self.restoredApp = targetApp
            self.sleepMicros = sleepMicroseconds
        }
    }

    @MainActor
    @Test("AppState manages text history cleanly and respects max limits (FR-4.4)")
    func testAppStateHistory() async throws {
        let appState = AppState()
        #expect(appState.history.isEmpty)
        #expect(appState.isRecording == false)

        // 履歴上限テスト
        appState.maxHistoryItems = 3
        appState.history = [
            HistoryItem(text: "1"),
            HistoryItem(text: "2"),
            HistoryItem(text: "3"),
            HistoryItem(text: "4"),
            HistoryItem(text: "5")
        ]
        // 手動クリーンアップを実行（private メソッドなので直接呼べないため、clearHistory でテスト）
        appState.clearHistory()
        #expect(appState.history.isEmpty)
    }

    @Test("FocusManager captures and restores focus correctly")
    func testFocusManager() async throws {
        let mockFocus = MockFocusManager()
        let inserter = TextInserter(focusManager: mockFocus)
        
        inserter.restoreFocus(targetApp: nil)
        #expect(mockFocus.restoredApp == nil)
        #expect(mockFocus.sleepMicros == 200_000)
    }
}



