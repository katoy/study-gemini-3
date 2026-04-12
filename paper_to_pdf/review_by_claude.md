# プロジェクトレビュー結果 (paper-to-pdf)

## レビュー対象情報
- **Branch**: work
- **最終更新**: 2026-04-12

---

## セッション 1（旧来レビュー）

### 概要
DewarpNet 統合・パラメータ最適化・テスト網羅率 100% 達成を実施。

### 評価
- DewarpNet のクリーンな設計・フォールバック機構・デバイス最適化
- ビジュアル回帰テストの導入（エンドツーエンド検証）
- pre-commit フックによるカバレッジ強制

---

## セッション 2（2026-04-12 コードレビューと全修正）

### 実施内容

全ソースファイルをレビューし、🔴即修正 5 件・🟠修正推奨 7 件・バグ修正 1 件を対応した。
テスト件数：303 → 309 件、カバレッジ：100% を維持。

---

### 🔴 即修正（対応済み）

| # | ファイル | 問題 | 修正 |
|---|---|---|---|
| 1 | `page_detector.py` | `order_points` の `np.diff` が不明瞭で縮退四角形に未対応 | `pts[:,1]-pts[:,0]` に明瞭化。同一点が複数コーナーに割り当てられる縮退ケースは重心角度ソートでフォールバック |
| 2 | `dewarper.py` | `cv2.remap` の `map_x/map_y` 引数に対する `bm` チャンネル順序の根拠がコード内に明示なし | `bm[:,：,0]=x, bm[:,：,1]=y` の対応と `cv2.remap` の仕様をコメントで文書化 |
| 3 | `processor.py` | `cv2.imwrite` 失敗時だけ `IOError` を即時投げ、他エラーは `continue` する不一貫 | 失敗時を `failed_images` に追加して `continue` に統一。テストも更新 |
| 4 | `image_processor.py` | `_MAX_KERNEL = 255` が大解像度画像で `cv2.dilate` の処理時間急増リスク | 127 に削減。コメントで理由を明示 |
| 5 | `pdf_builder.py` | Pillow フォールバックが全ページをメモリに乗せるが制限なし | 300 ページ超で `MemoryError`。51 ページ超で推定メモリ量を WARNING ログ出力 |

---

### 🟠 修正推奨（対応済み）

| # | ファイル | 問題 | 修正 |
|---|---|---|---|
| 1 | `page_detector.py:117` | `M['m00']` ゼロガードがサイレントスキップ | `logger.warning` を追加して観測可能にした |
| 2 | `dewarper.py:127` | ライン検出失敗時に `0.0` を返すと「湾曲なし」と誤解釈され DewarpNet/polynomial 両方スキップ | 戻り値を `None`（湾曲不明）に変更。DewarpNet は `None` でも試みる。polynomial は `None` でスキップ |
| 3 | `image_processor.py:122` | `deskew_page` が図版・白紙ページでも傾き補正を試みる | テキスト密度ガード追加（dark_ratio < 0.5% または > 50% はスキップ） |
| 4 | `steps/quality_check.py:88` | テキスト見切れ検出の `margin_threshold` が固定 10%。高密度ページで誤検出リスク | `max(0.10, overall_density * 0.5)` の適応的閾値に変更 |
| 5 | `processor.py:161` | 失敗率閾値 50% が高すぎ | 25% に引き下げ。`_MAX_FAILURE_RATE` 定数で管理 |
| 6 | `tests/test_utils_image.py` | `extract_line_profiles` のテストが基本形のみ | 湾曲ライン検出・weight 正値確認・マージン除外の 4 件を追加 |
| 7 | `tests/test_visual_regression.py:105` | `UPDATE_GOLDENS=1` で全黒/全白の破損画像が無条件に golden 化される | 書き込み前に `mean/std` チェックし疑わしい値は `UserWarning` を発出 |

---

### 🐛 バグ修正（今回発見）

| ファイル | 問題 | 修正 |
|---|---|---|
| `steps/quality_check.py:260` | 縦書きページの湾曲検出で `extract_line_profiles`（水平エッジ検出）をそのまま使用。縦列の文字境界が「湾曲した横ライン」として誤検出され、正常ページに 5.6% の偽湾曲値が出て警告が発生していた | `is_vertical=True` 時は画像を 90° 回転してから `extract_line_profiles` を呼ぶよう修正。`dewarper._estimate_curvature_percent` と同じアプローチ |

---

### 🟡 設計・可読性（未対応・今後の検討事項）

| # | ファイル | 提案 |
|---|---|---|
| 1 | `core/config.py` | `__post_init__` のバリデーションをdict化して肥大化を防ぐ |
| 2 | `processor.py` | `run()` メソッド（130行）を `_create_pipeline / _load_images / _run_pipeline` に分割 |
| 3 | `page_detector.py` | `find_center_seam` の 3 戦略を個別関数に抽出 |
| 4 | `dewarper.py` | `_DewarpNetContentError` を `DewarpingError` 基底クラスに整理 |
| 5 | `core/pipeline.py` | エラー時のサイレントフォールバックにモード切替（strict/fallback）を追加 |
| 6 | 複数ファイル | マジックナンバーを `constants.py` に集約 |
| 7 | 複数ファイル | `logger.debug/info` の使い分けを統一（INFO=ユーザー向け、DEBUG=開発者向け） |

---

## 現状評価

**判定: 承認 (Excellent)**

- テスト 309 件・カバレッジ 100% を維持
- 縦書きモードの偽陽性品質警告を解消
- 即修正・修正推奨の全 12 件に対応済み
- 残課題は設計/可読性の改善のみ（機能・品質への影響なし）
