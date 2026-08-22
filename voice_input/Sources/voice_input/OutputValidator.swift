import Foundation

/// ASR出力の品質・安全性を検証する検証器 (FR-2.4)
public struct OutputValidator: Sendable {
    public enum ValidationResult: Equatable, Sendable {
        case valid
        case empty
        case repetitiveLoop(pattern: String)
        case languageMismatch(detectedLanguage: String)  // 日本語以外が検出された
    }

    /// 言語判定用の言語コード定義
    private enum DetectedLanguage: Equatable {
        case japanese
        case english
        case mixed
        case unknown
    }

    public init() {}

    /// ASR転写テキストに対する検証を実施する
    public func validate(text: String) -> ValidationResult {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return .empty
        }

        // 言語判定 (FR-2.4: 日本語以外の混入検知)
        let detectedLanguage = detectLanguage(in: trimmed)
        if detectedLanguage != .japanese && detectedLanguage != .mixed {
            let langName = detectedLanguage == .english ? "英語" : "不明な言語"
            return .languageMismatch(detectedLanguage: langName)
        }

        // 繰り返しループの検出 (3回以上の連続同一文字または単語/パターンの繰り返し)
        if let repeatedPattern = detectRepetitiveLoop(in: trimmed) {
            return .repetitiveLoop(pattern: repeatedPattern)
        }

        return .valid
    }

    /// テキストの主言語を検出
    private func detectLanguage(in text: String) -> DetectedLanguage {
        var japaneseCount = 0
        var englishCount = 0

        for scalar in text.unicodeScalars {
            // 日本語文字（ひらがな、カタカナ、漢字）
            if (0x3040...0x309F).contains(scalar.value) ||  // ひらがな
               (0x30A0...0x30FF).contains(scalar.value) ||  // カタカナ
               (0x4E00...0x9FFF).contains(scalar.value) {   // 漢字
                japaneseCount += 1
            }
            // 英語（a-z, A-Z）
            else if (scalar.value >= 0x61 && scalar.value <= 0x7A) ||
                    (scalar.value >= 0x41 && scalar.value <= 0x5A) {
                englishCount += 1
            }
        }

        let totalRelevantChars = japaneseCount + englishCount
        guard totalRelevantChars > 0 else {
            return .unknown
        }

        let japaneseRatio = Double(japaneseCount) / Double(totalRelevantChars)

        // 日本語が 80% 以上なら日本語、20% 以上なら混在、20% 未満なら英語
        if japaneseRatio >= 0.8 {
            return .japanese
        } else if japaneseRatio >= 0.2 {
            return .mixed
        } else {
            return .english
        }
    }

    /// 繰り返しループの検知ロジック
    private func detectRepetitiveLoop(in text: String) -> String? {
        let count = text.count
        guard count >= 6 else { return nil }

        let characters = Array(text)

        // 1〜15文字のサブ文字列パターンの繰り返しチェック
        for patternLength in 1...min(15, count / 3) {
            var matchCount = 1
            let pattern = String(characters[0..<patternLength])

            var index = patternLength
            while index + patternLength <= count {
                let sub = String(characters[index..<(index + patternLength)])
                if sub == pattern {
                    matchCount += 1
                    if matchCount >= 3 {
                        return pattern
                    }
                } else {
                    break
                }
                index += patternLength
            }
        }

        return nil
    }
}
