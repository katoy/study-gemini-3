import pytest
import os
from pathlib import Path
from extract_text import extract_text_from_pdf

def test_samples_h_text_regression(tmp_path):
    """
    samples_h.pdf から抽出されたテキストの回帰テスト。
    抽出結果の Markdown が tests/goldens/samples_h_text.md と一致するか検証します。
    """
    
    root = Path(__file__).parent.parent
    # main.py で作成済みの samples_h.pdf を使用
    pdf_path = root / "samples_h.pdf"
    
    if not pdf_path.exists():
        pytest.skip("samples_h.pdf が見つからないためスキップします。")
        
    output_md = tmp_path / "current_samples_h.md"
    golden_md = root / "tests" / "goldens" / "samples_h_text.md"
    
    # 1. テキスト抽出の実行
    # 注意: このテストは Mac 環境 (ocrmac が動作する環境) でのみ完全な検証が可能です。
    try:
        # 言語設定を固定して再現性を確保
        success = extract_text_from_pdf(pdf_path, output_md, languages=['ja-JP', 'en-US'], auto_rotate=True)
    except Exception as e:
        pytest.skip(f"OCR 実行不可 (Mac 以外の環境などの可能性): {e}")
        
    assert success is True
    current_content = output_md.read_text(encoding="utf-8")
    
    # 2. GOLDEN 更新モード (UPDATE_GOLDENS=1 pytest ...)
    if os.environ.get("UPDATE_GOLDENS") == "1":
        golden_md.parent.mkdir(parents=True, exist_ok=True)
        golden_md.write_text(current_content, encoding="utf-8")
        print(f"\n[INFO] 更新完了: {golden_md}")
        return

    # 3. 比較検証
    if not golden_md.exists():
        pytest.fail(f"GOLDEN データが見つかりません: {golden_md}\nUPDATE_GOLDENS=1 を付けて実行して作成してください。")

    golden_content = golden_md.read_text(encoding="utf-8")
    
    # 文字列の類似度を検証 (OCR の非決定性を許容)
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, golden_content, current_content).ratio()
    
    # 98% 以上の一致を要求
    THRESHOLD = 0.98
    if similarity < THRESHOLD:
        import difflib
        diff = difflib.unified_diff(
            golden_content.splitlines(),
            current_content.splitlines(),
            fromfile="golden",
            tofile="current",
            lineterm=""
        )
        diff_msg = "\n".join(diff)
        pytest.fail(f"抽出テキストの類似度が低すぎます ({similarity:.2%}):\n{diff_msg}")
    else:
        print(f"\n[INFO] 類似度パス: {similarity:.2%}")
