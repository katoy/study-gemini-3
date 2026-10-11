#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pypdf",
# ]
# ///
"""
bench/results/<エンジン名>/ の OCR 結果を比較し、Markdown の表を出力する。
--samples / --results で縦書き用などの別セットを指定できる。

指標:
- CER: 正解テキスト (samples/*.gt.txt) との文字誤り率。NFKC 正規化と空白除去の後に計算する
- 和文間空白: 和文文字にはさまれた空白の数（目次・章検出の正規表現を壊す原因）
- 章検出: scripts/pdf_chapter_pipeline.py の detect_chapters_by_keywords で検出できたページ
- 秒/ページ: 1 ページあたりの平均処理時間
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR.parent / "scripts"))

from pdf_chapter_pipeline import detect_chapters_by_keywords  # noqa: E402

# Kindle のタイトルバー・フッター（読了までの時間、進捗率）。本文ではないので CER の計算から除く
NON_BODY_RE = re.compile(r"^(Kindle|章を読み終えるまで.*|\d+%)$")
CJK = r"[぀-ヿ㐀-鿿！-｠]"
CJK_SPACE_RE = re.compile(rf"(?<={CJK})[ \t　]+(?={CJK})")
# 章見出しを含むサンプルページ（目視で確認済み）
CHAPTER_PAGES = {"k13_p007", "k13_p008", "k13_p018", "k13_p019", "k13_p045"}


class _FakePage:
    """detect_chapters_by_keywords に渡すための PdfReader.pages 要素の代用品。"""

    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    def __init__(self, texts: list[str]) -> None:
        self.pages = [_FakePage(t) for t in texts]


def normalize(text: str) -> str:
    """CER 用の正規化（タイトルバー行の除去、NFKC、空白除去）。"""
    lines = [line for line in text.splitlines() if not NON_BODY_RE.match(line.strip())]
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", "\n".join(lines)))


def edit_distance(a: str, b: str) -> int:
    """レーベンシュタイン距離を返す。"""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def detected_chapter_pages(stems: list[str], texts: list[str]) -> set[str]:
    """パイプラインのキーワード検出で章扱いになったページ名を返す。"""
    entries = detect_chapters_by_keywords(_FakeReader(texts))  # type: ignore[arg-type]
    return {stems[e.physical_page - 1] for e in entries}


def evaluate(engine_dir: Path, samples_dir: Path) -> dict[str, str]:
    """1 エンジン分の指標を計算する。"""
    outputs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(engine_dir.glob("*.txt"))}
    timings = json.loads((engine_dir / "timings.json").read_text(encoding="utf-8"))

    errors = total = 0
    for gt_path in sorted(samples_dir.glob("*.gt.txt")):
        stem = gt_path.name.removesuffix(".gt.txt")
        gt = normalize(gt_path.read_text(encoding="utf-8"))
        errors += edit_distance(normalize(outputs.get(stem, "")), gt)
        total += len(gt)

    stems = list(outputs)
    raw_hits = detected_chapter_pages(stems, list(outputs.values()))
    chapter_pages = CHAPTER_PAGES & set(stems)
    nfkc_hits = detected_chapter_pages(
        stems, [unicodedata.normalize("NFKC", t) for t in outputs.values()]
    )
    spaces = sum(len(CJK_SPACE_RE.findall(t)) for t in outputs.values())
    n = len(chapter_pages)
    return {
        "engine": engine_dir.name,
        "cer": f"{errors / total:.1%}",
        "spaces": str(spaces),
        "chapters": f"{len(raw_hits & chapter_pages)}/{n}" if n else "-",
        "chapters_nfkc": f"{len(nfkc_hits & chapter_pages)}/{n}" if n else "-",
        "false_chapters": str(len(nfkc_hits - chapter_pages)),
        "sec": f"{sum(timings.values()) / len(timings):.2f}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=BENCH_DIR / "samples")
    parser.add_argument("--results", type=Path, default=BENCH_DIR / "results")
    args = parser.parse_args()

    rows = [evaluate(d, args.samples) for d in sorted(args.results.iterdir()) if d.is_dir()]
    print("| エンジン | CER | 和文間空白 | 章検出 | 章検出 (NFKC 後) | 誤検出 | 秒/ページ |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(
            f"| {r['engine']} | {r['cer']} | {r['spaces']} | {r['chapters']} "
            f"| {r['chapters_nfkc']} | {r['false_chapters']} | {r['sec']} |"
        )


if __name__ == "__main__":
    main()
