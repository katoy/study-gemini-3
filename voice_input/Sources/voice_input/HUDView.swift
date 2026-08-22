import SwiftUI

/// 常駐メニューバー HUD ビュー (FR-1.3, FR-4.3, FR-6.1)
public struct HUDView: View {
    @ObservedObject var appState: AppState
    @State private var selectedTab = 0
    @State private var newReading = ""
    @State private var newTarget = ""
    
    public init(appState: AppState) {
        self.appState = appState
    }
    
    public var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("音声入力").tag(0)
                Text("履歴").tag(1)
                Text("辞書").tag(2)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 8)
            
            Divider()
            
            if selectedTab == 0 {
                mainVoiceInputView
            } else if selectedTab == 1 {
                historyView
            } else {
                dictionaryView
            }
        }
        .frame(width: 340, height: 220)
    }
    
    // MARK: - メイン音声入力タブ
    @ViewBuilder
    private var mainVoiceInputView: some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                Circle()
                    .fill(appState.isRecording ? Color.red : Color.green)
                    .frame(width: 10, height: 10)
                
                Text(appState.statusMessage)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.primary)
                
                Spacer()
                
                Button(action: {
                    appState.toggleRecording()
                }) {
                    Text(appState.isRecording ? "停止 (Opt+Space)" : "録音開始")
                        .font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.isRecording ? .red : .blue)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text("プレビュー / 最新結果:")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                
                ScrollView {
                    Text(appState.previewText.isEmpty ? "マイクから音声を発話してください" : appState.previewText)
                        .font(.system(size: 13))
                        .foregroundColor(appState.previewText.isEmpty ? .secondary : .primary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .background(Color.secondary.opacity(0.1))
                .cornerRadius(6)
            }
        }
        .padding(12)
    }
    
    // MARK: - 履歴タブ (FR-4.3, FR-4.4)
    @ViewBuilder
    private var historyView: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("履歴一覧 (\(appState.history.count)件)")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                Spacer()
                if !appState.history.isEmpty {
                    Button("一括削除") {
                        appState.clearHistory()
                    }
                    .font(.system(size: 11))
                    .buttonStyle(.borderless)
                    .foregroundColor(.red)
                }
            }
            
            if appState.history.isEmpty {
                Text("履歴はありません")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            } else {
                List(appState.history, id: \.id) { item in
                    HStack {
                        Text(item.text)
                            .font(.system(size: 12))
                            .lineLimit(2)
                        Spacer()
                        Button(action: {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(item.text, forType: .string)
                        }) {
                            Image(systemName: "doc.on.doc")
                                .font(.system(size: 11))
                        }
                        .buttonStyle(.borderless)
                    }
                }
                .listStyle(.inset)
            }
        }
        .padding(8)
    }
    
    // MARK: - ユーザー辞書タブ (FR-6.1)
    @ViewBuilder
    private var dictionaryView: some View {
        VStack(spacing: 8) {
            HStack(spacing: 6) {
                TextField("読み (例: クロード)", text: $newReading)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
                TextField("表記 (例: Claude)", text: $newTarget)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
                Button("追加") {
                    appState.dictionaryManager.add(reading: newReading, target: newTarget)
                    newReading = ""
                    newTarget = ""
                }
                .buttonStyle(.bordered)
                .font(.system(size: 11))
            }
            
            List(appState.dictionaryManager.items) { item in
                HStack {
                    Text("\(item.reading) → \(item.target)")
                        .font(.system(size: 12))
                    Spacer()
                    Button(action: {
                        appState.dictionaryManager.remove(id: item.id)
                    }) {
                        Image(systemName: "trash")
                            .font(.system(size: 11))
                            .foregroundColor(.red)
                    }
                    .buttonStyle(.borderless)
                }
            }
            .listStyle(.inset)
        }
        .padding(8)
    }
}

