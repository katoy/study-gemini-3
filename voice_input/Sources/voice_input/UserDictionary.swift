import Foundation

/// ユーザー辞書アイテム (FR-6.1)
public struct UserDictionaryItem: Codable, Equatable, Sendable, Identifiable {
    public var id: UUID
    public var reading: String  // 読み (例: クロード)
    public var target: String   // 表記 (例: Claude)
    public var isEnabled: Bool

    public init(id: UUID = UUID(), reading: String, target: String, isEnabled: Bool = true) {
        self.id = id
        self.reading = reading
        self.target = target
        self.isEnabled = isEnabled
    }
}

/// ユーザー辞書マネージャ (FR-6)
public final class UserDictionaryManager: @unchecked Sendable {
    private(set) public var items: [UserDictionaryItem] = []
    
    public init(initialItems: [UserDictionaryItem]? = nil) {
        if let initialItems = initialItems {
            self.items = initialItems
        } else {
            self.items = [
                UserDictionaryItem(reading: "クロード", target: "Claude"),
                UserDictionaryItem(reading: "ジェミニ", target: "Gemini"),
                UserDictionaryItem(reading: "マック", target: "Mac")
            ]
        }
    }

    public func add(reading: String, target: String) {
        let trimmedReading = reading.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedTarget = target.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedReading.isEmpty, !trimmedTarget.isEmpty else { return }

        if let existingIndex = items.firstIndex(where: { $0.reading == trimmedReading }) {
            items[existingIndex].target = trimmedTarget
            items[existingIndex].isEnabled = true
        } else {
            items.append(UserDictionaryItem(reading: trimmedReading, target: trimmedTarget))
        }
    }

    public func remove(id: UUID) {
        items.removeAll(where: { $0.id == id })
    }

    /// 有効な辞書項目を [読み: 表記] 辞書として取得 (FR-6.2)
    public func activeDictionary() -> [String: String] {
        var dict: [String: String] = [:]
        for item in items where item.isEnabled {
            dict[item.reading] = item.target
        }
        return dict
    }

    /// JSON エクスポート (FR-6.3)
    public func exportJSON() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        return try encoder.encode(items)
    }

    /// JSON インポート (FR-6.3)
    public func importJSON(_ data: Data) throws {
        let decoder = JSONDecoder()
        let decoded = try decoder.decode([UserDictionaryItem].self, from: data)
        self.items = decoded
    }

    /// CSV エクスポート (FR-6.3)
    /// CSV フォーマット: reading,target,isEnabled
    public func exportCSV() throws -> Data {
        var csvText = "reading,target,isEnabled\n"
        for item in items {
            let reading = escapeCSVField(item.reading)
            let target = escapeCSVField(item.target)
            csvText += "\(reading),\(target),\(item.isEnabled)\n"
        }
        guard let data = csvText.data(using: .utf8) else {
            throw NSError(domain: "UserDictionaryManager", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "CSV エンコードに失敗しました。"
            ])
        }
        return data
    }

    /// CSV インポート (FR-6.3)
    public func importCSV(_ data: Data) throws {
        guard let csvText = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "UserDictionaryManager", code: 2, userInfo: [
                NSLocalizedDescriptionKey: "CSV デコードに失敗しました。"
            ])
        }

        let lines = csvText.components(separatedBy: .newlines)
        var decoded: [UserDictionaryItem] = []

        for (index, line) in lines.enumerated() {
            // ヘッダー行をスキップ
            if index == 0 || line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                continue
            }

            let fields = parseCSVLine(line)
            guard fields.count >= 2 else { continue }

            let reading = fields[0]
            let target = fields[1]
            let isEnabled = fields.count > 2 ? (fields[2].lowercased() == "true") : true

            decoded.append(UserDictionaryItem(reading: reading, target: target, isEnabled: isEnabled))
        }

        self.items = decoded
    }

    /// CSV フィールドのエスケープ
    private func escapeCSVField(_ field: String) -> String {
        if field.contains(",") || field.contains("\"") || field.contains("\n") {
            return "\"\(field.replacingOccurrences(of: "\"", with: "\"\""))\""
        }
        return field
    }

    /// CSV 行のパース（ダブルクォート対応）
    private func parseCSVLine(_ line: String) -> [String] {
        var fields: [String] = []
        var currentField = ""
        var inQuotes = false

        for char in line {
            if char == "\"" {
                inQuotes.toggle()
            } else if char == "," && !inQuotes {
                fields.append(currentField.trimmingCharacters(in: .whitespaces))
                currentField = ""
            } else {
                currentField.append(char)
            }
        }

        fields.append(currentField.trimmingCharacters(in: .whitespaces))
        return fields
    }
}
