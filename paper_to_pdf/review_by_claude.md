# プロジェクトレビュー結果 (paper-to-pdf)

## レビュー対象情報

| 項目 | 内容 |
|---|---|
| Branch | work |
| 最終更新 | 2026-04-12 |
| テスト件数 | 317 件 |
| カバレッジ | 100% |
| 判定 | **承認 (Excellent)** |

---

## 対応済み一覧

### 🔴 即修正（5件）

| # | ファイル | 問題 | 修正 |
|---|---|---|---|
| 1 | `page_detector.py` | `order_points` の縮退四角形未対応 | 重心角度ソートでフォールバック |
| 2 | `dewarper.py` | `bm` チャンネル順序の根拠が未明示 | コメントで文書化 |
| 3 | `processor.py` | `cv2.imwrite` 失敗時の挙動が不一貫 | `failed_images` に追加して `continue` に統一 |
| 4 | `image_processor.py` | `_MAX_KERNEL=255` で大解像度時に処理時間急増 | 127 に削減 |
| 5 | `pdf_builder.py` | Pillow フォールバックがメモリ無制限 | 51 ページ超で推定メモリ量 WARNING ログ |

### 🟠 修正推奨（7件）

| # | ファイル | 問題 | 修正 |
|---|---|---|---|
| 1 | `page_detector.py` | `M['m00']` ゼロガードがサイレントスキップ | `logger.warning` 追加 |
| 2 | `dewarper.py` | ライン検出失敗時 `0.0` 返却で「湾曲なし」と誤解釈 | `None`（湾曲不明）に変更 |
| 3 | `image_processor.py` | 図版・白紙でも傾き補正実行 | テキスト密度ガード追加 |
| 4 | `steps/quality_check.py` | `margin_threshold` 固定 10% で誤検出 | `max(0.10, density * 0.5)` の適応的閾値に変更 |
| 5 | `processor.py` | 失敗率閾値 50% が高すぎ | 25% に引き下げ（`_MAX_FAILURE_RATE` 定数化） |
| 6 | `tests/test_utils_image.py` | `extract_line_profiles` テストが基本形のみ | 4 件追加 |
| 7 | `tests/test_visual_regression.py` | 破損画像が無条件に golden 化される | 書き込み前に `mean/std` チェックし `UserWarning` 発出 |

### 🐛 バグ修正（1件）

| ファイル | 問題 | 修正 |
|---|---|---|
| `steps/quality_check.py` | 縦書きページで水平エッジ検出を誤用し偽湾曲警告が発生 | `is_vertical=True` 時に 90° 回転してから処理 |

### 🟡 設計・可読性（7件）

| # | ファイル | 内容 | コミット |
|---|---|---|---|
| 1 | `core/config.py` | `__post_init__` バリデーションを dict 化 | 06b9f63 |
| 2 | `processor.py` | `run()` を `_create_pipeline / _load_images / _run_pipeline` に分割 | 83f7b55 |
| 3 | `page_detector.py` | `find_center_seam` の 3 戦略を独立関数に抽出 | 655c915 |
| 4 | `dewarper.py` | `DewarpError` 基底クラス階層を整理 | ffdb303 |
| 5 | `core/pipeline.py` | strict モード追加（エラー再送出） | b3c91e2 |
| 6 | 複数ファイル | マジックナンバーを `constants.py` に集約 | 9f6551b |
| 7 | 複数ファイル | `logger.info/debug` の使い分けを統一（INFO=ユーザー向け、DEBUG=開発者向け） | — |

### 🔵 テスト強化（2件）

| 内容 | 詳細 |
|---|---|
| ビジュアル回帰テストにログ出力チェックを追加 | `_LogCapture` ハンドラで WARNING+ を収集し `warnings.txt` と差分比較。新規警告・消失警告を自動検出 |
| `.coveragerc` に変換スクリプトを追加 | `convert_docling.py` 等の未追跡スクリプトをカバレッジ除外 |

**ログ golden の現状：**

| テスト | WARNING 行数 | 主な内容 |
|---|---|---|
| `synthetic` | 3 | 品質チェック：文字見切れ検出 |
| `samples_h_dewarpnet` | 2 | DewarpNet→polynomial 永続切替 |
| `samples_h_polynomial` | 0 | — |
| `samples_v` | 0 | — |

---

## 現状評価

**判定: 承認 (Excellent)**

- テスト 317 件・カバレッジ 100% を維持
- 即修正 5・修正推奨 7・バグ修正 1・設計改善 7 件すべて対応済み
- ビジュアル回帰テストで画像品質とログ出力の両方を検出可能
- 残課題なし
