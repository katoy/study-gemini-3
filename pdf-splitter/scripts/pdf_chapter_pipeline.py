#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pypdf",
#     "ocrmypdf",
#     "pikepdf",
# ]
# ///
"""
OCR → 目次解析 → 章分割パイプライン。

スキャンPDF (Kindle等) を ocrmypdf で検索可能化し、
OCR後の目次テキストを解析して章の開始ページを推定して分割、
20MB超ファイルをさらに分割する。
"""

import argparse
import difflib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter

import pdf_utils


@dataclass
class TocEntry:
    """目次の1行分（タイトル、ページ番号等）。"""
    title: str
    printed_page: int
    is_chapter: bool
    physical_page: Optional[int] = None


def find_toc_pages(reader: PdfReader, scan_limit: int = 30) -> list[int]:
    """
    先頭scan_limitページから目次ページのインデックス (0-based) を返す。
    「目次」キーワード、または「タイトル + ドット/空白 + ページ番号」の密度で判定。
    """
    toc_line_patterns = [
        re.compile(r'^(?P<title>.+?)\s*[\.․…⋯・‥…]{2,}\s*(?P<page>\d{1,4})\s*$'),
        re.compile(r'^(?P<title>\S(?:.*\S)?)\s{2,}(?P<page>\d{1,4})\s*$'),
    ]
    keyword_re = re.compile(r'(目次|もくじ|Contents|CONTENTS)', re.IGNORECASE)

    def line_match_stats(text: str):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return 0, 0.0
        matches = sum(1 for l in lines if any(p.match(l) for p in toc_line_patterns))
        ratio = matches / len(lines) if lines else 0.0
        return matches, ratio

    n = min(scan_limit, len(reader.pages))
    start = None
    for i in range(n):
        text = reader.pages[i].extract_text() or ""
        matches, ratio = line_match_stats(text)
        head_text = "\n".join(text.splitlines()[:5])
        has_keyword = bool(keyword_re.search(head_text))
        if has_keyword or (matches >= 3 and ratio >= 0.3):
            start = i
            break

    if start is None:
        return []

    toc_pages = [start]
    i = start + 1
    while i < min(scan_limit + 10, len(reader.pages)):
        text = reader.pages[i].extract_text() or ""
        matches, ratio = line_match_stats(text)
        if matches >= 3 or ratio >= 0.3:
            toc_pages.append(i)
            i += 1
        else:
            break

    return toc_pages


def parse_toc_entries(reader: PdfReader, toc_page_indices: list[int]) -> list[TocEntry]:
    """目次ページをパースして (タイトル, 印字ページ番号) の一覧を返す。"""
    toc_line_patterns = [
        re.compile(r'^(?P<title>.+?)\s*[\.․…⋯・‥…]{2,}\s*(?P<page>\d{1,4})\s*$'),
        re.compile(r'^(?P<title>\S(?:.*\S)?)\s{2,}(?P<page>\d{1,4})\s*$'),
    ]
    chapter_re = re.compile(
        r'^(第\s*[0-9〇一二三四五六七八九十百]+\s*章'
        r'|Chapter\s*\d+|CHAPTER\s*\d+'
        r'|はじめに|まえがき|序章|プロローグ'
        r'|おわりに|あとがき|エピローグ|付録|索引|Appendix|Index)',
        re.IGNORECASE,
    )

    entries = []
    for idx in toc_page_indices:
        text = reader.pages[idx].extract_text() or ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = next((p.match(line) for p in toc_line_patterns if p.match(line)), None)
            if not m:
                continue
            title = m.group("title").strip(" .・‥…")
            try:
                page_num = int(m.group("page"))
            except ValueError:
                continue
            if not title or page_num <= 0:
                continue
            is_chapter = bool(chapter_re.match(title))
            entries.append(TocEntry(title, page_num, is_chapter))

    return entries


def normalize(s: str) -> str:
    """テキスト正規化（空白除去、NFKC正規化）。"""
    return re.sub(r'\s+', '', unicodedata.normalize("NFKC", s))


def compute_offset(reader: PdfReader, entries: list[TocEntry], sample_size: int = 4, threshold: float = 0.55) -> Optional[int]:
    """
    印字ページ番号から物理ページ番号へのオフセットを推定。
    章レベルエントリの先頭数件について、複数のオフセット候補を試し、
    ページ先頭のテキストとタイトルを類似度比較して投票。
    過半数合意が取れたオフセットを返す。
    """
    chapter_entries = [e for e in entries if e.is_chapter][:sample_size]
    if len(chapter_entries) < 2:
        return None

    total_pages = len(reader.pages)
    votes = {}
    offset_range = range(-5, 60)

    for entry in chapter_entries:
        best_offset, best_score = None, 0.0
        norm_title = normalize(entry.title)
        if not norm_title:
            continue

        for offset in offset_range:
            phys = entry.printed_page + offset
            if not (1 <= phys <= total_pages):
                continue
            page_text = reader.pages[phys - 1].extract_text() or ""
            head = normalize("\n".join(page_text.splitlines()[:6]))
            score = difflib.SequenceMatcher(None, norm_title, head).ratio()
            if norm_title in normalize(page_text[:400]):
                score = max(score, 0.9)
            if score > best_score:
                best_score, best_offset = score, offset

        if best_offset is not None and best_score >= threshold:
            votes[best_offset] = votes.get(best_offset, 0) + 1

    if not votes:
        return None

    offset, agree = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    if agree < max(1, len(chapter_entries) // 2):
        return None

    return offset


def build_chapter_boundaries(entries: list[TocEntry], offset: int, total_pages: int) -> list[TocEntry]:
    """
    物理ページ番号を設定し、逆転・重複を除去した章エントリを返す。
    """
    chapter_entries = sorted(
        (e for e in entries if e.is_chapter),
        key=lambda e: e.printed_page,
    )
    cleaned, last_page = [], 0
    for e in chapter_entries:
        phys = e.printed_page + offset
        if 1 <= phys <= total_pages and phys > last_page:
            e.physical_page = phys
            cleaned.append(e)
            last_page = phys
    return cleaned


def sanitize_filename(title: str, max_len: int = 40) -> str:
    """ファイル名として使える形に正規化。"""
    title = re.sub(r'[\\/:*?"<>|]', '', title).strip().replace(' ', '_')
    return (title or "untitled")[:max_len]


def split_by_boundaries(
    reader: PdfReader,
    boundary_entries: list[TocEntry],
    output_dir: Path,
) -> list[dict]:
    """
    章の開始ページをもとに分割して、出力ファイル情報の辞書リストを返す。
    """
    total_pages = len(reader.pages)
    starts = [e.physical_page for e in boundary_entries]
    titles = [e.title for e in boundary_entries]

    if starts[0] > 1:
        starts = [1] + starts
        titles = ["前付け"] + titles

    ends = starts[1:] + [total_pages + 1]

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for i, (start, end, title) in enumerate(zip(starts, ends, titles), start=1):
        writer = PdfWriter()
        for p in range(start - 1, end - 1):
            writer.add_page(reader.pages[p])
        fname = f"{i:02d}_{sanitize_filename(title)}_p{start}-{end-1}.pdf"
        out_path = output_dir / fname
        with open(out_path, "wb") as f:
            writer.write(f)
        outputs.append({
            "path": str(out_path),
            "title": title,
            "start": start,
            "end": end - 1,
            "size_mb": out_path.stat().st_size / (1024 ** 2),
        })

    return outputs


def resplit_oversized(
    reader: PdfReader,
    chapter_info: dict,
    all_entries: list[TocEntry],
    output_dir: Path,
    max_size_mb: float,
    index_prefix: str,
) -> list[dict]:
    """
    20MB超のファイルを再分割。目次の細目をもとに分割位置を決める。
    """
    path = Path(chapter_info["path"])
    size_mb = path.stat().st_size / (1024 ** 2)
    if size_mb <= max_size_mb:
        return [chapter_info]

    start, end = chapter_info["start"], chapter_info["end"]
    page_count = end - start + 1
    num_parts = max(2, math.ceil(size_mb / max_size_mb))

    fine_candidates = sorted({
        e.physical_page for e in all_entries
        if e.physical_page and start < e.physical_page <= end
    })

    cut_points = []
    remaining = list(fine_candidates)
    for k in range(1, num_parts):
        target = start + round(page_count * k / num_parts)
        tolerance = max(5, page_count // (2 * num_parts))
        best = min(remaining, key=lambda p: abs(p - target)) if remaining else None
        if best is not None and abs(best - target) <= tolerance:
            cut_points.append(best)
            remaining.remove(best)
        else:
            cut_points.append(target)

    cut_points = sorted(set(p for p in cut_points if start < p <= end))
    sub_starts = [start] + cut_points
    sub_ends = cut_points + [end + 1]

    path.unlink()
    outputs = []
    for j, (s, e) in enumerate(zip(sub_starts, sub_ends), start=1):
        writer = PdfWriter()
        for p in range(s - 1, e - 1):
            writer.add_page(reader.pages[p])
        fname = f"{index_prefix}_{sanitize_filename(chapter_info['title'])}_part{j}_p{s}-{e-1}.pdf"
        out_path = output_dir / fname
        with open(out_path, "wb") as f:
            writer.write(f)
        sub_info = {
            "path": str(out_path),
            "title": f"{chapter_info['title']} (part{j})",
            "start": s,
            "end": e - 1,
            "size_mb": out_path.stat().st_size / (1024 ** 2),
        }
        result = recursive_bisect_if_needed(reader, sub_info, output_dir, max_size_mb)
        outputs.extend(result)

    return outputs


def recursive_bisect_if_needed(
    reader: PdfReader,
    info: dict,
    output_dir: Path,
    max_size_mb: float,
    depth: int = 0,
) -> list[dict]:
    """
    20MB超が残った場合、再帰的に二分割。深さ上限4、最小2ページで打ち切り。
    """
    path = Path(info["path"])
    size_mb = path.stat().st_size / (1024 ** 2)
    if size_mb <= max_size_mb or depth >= 4 or info["end"] - info["start"] < 2:
        return [info]

    mid = (info["start"] + info["end"]) // 2
    path.unlink()
    result = []
    for j, (s, e) in enumerate([(info["start"], mid), (mid + 1, info["end"])], start=1):
        writer = PdfWriter()
        for p in range(s - 1, e):
            writer.add_page(reader.pages[p])
        fname = f"{sanitize_filename(info['title'])}_bisect{j}_p{s}-{e}.pdf"
        out_path = output_dir / fname
        with open(out_path, "wb") as f:
            writer.write(f)
        sub_info = {
            "path": str(out_path),
            "title": f"{info['title']}-{j}",
            "start": s,
            "end": e,
            "size_mb": out_path.stat().st_size / (1024 ** 2),
        }
        result.extend(recursive_bisect_if_needed(reader, sub_info, output_dir, max_size_mb, depth + 1))

    return result


def detect_chapters_by_toc_titles(reader: PdfReader, toc_entries: list[TocEntry]) -> list[TocEntry]:
    """
    目次から取得した章名テキストをPDF内で検索し、実際の開始ページを特定。
    各章名が出現する最初のページを物理ページとして設定。
    """
    detected = []

    for entry in toc_entries:
        if not entry.is_chapter:
            continue

        norm_title = normalize(entry.title)
        if not norm_title or len(norm_title) < 2:
            continue

        best_match_page = None
        best_score = 0.0

        for page_idx in range(len(reader.pages)):
            try:
                page_text = reader.pages[page_idx].extract_text() or ""
                if not page_text.strip():
                    continue

                head_text = normalize("\n".join(page_text.splitlines()[:10]))
                score = difflib.SequenceMatcher(None, norm_title, head_text).ratio()

                if norm_title in head_text:
                    score = max(score, 0.95)

                if score > best_score:
                    best_score = score
                    best_match_page = page_idx + 1

                if score >= 0.8:
                    break

            except Exception:
                continue

        if best_match_page is not None and best_score >= 0.5:
            entry.physical_page = best_match_page
            detected.append(entry)

    return sorted(
        (e for e in detected if e.physical_page is not None),
        key=lambda e: e.physical_page,
    )


def detect_chapters_by_keywords(reader: PdfReader) -> list[TocEntry]:
    """
    PDF全体をスキャンして、トップレベルの章開始キーワード・章番号を検出。
    目次ページがない場合のフォールバック用。
    検出対象：「CHAPTER X」「第X章」などの大見出しのみ。
    細かいセクション番号（X.Y形式）は検出しない。
    """
    top_level_patterns = [
        re.compile(r'^(第\s*[0-9〇一二三四五六七八九十百]+\s*章)(?:\s+|$)', re.MULTILINE),
        re.compile(r'^(Chapter\s+\d+|CHAPTER\s+\d+)(?:\s+|$)', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^(Part\s+\d+|PART\s+\d+)(?:\s+|$)', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^(はじめに|まえがき|序章|プロローグ|Preface|Introduction|Prologue)(?:\s+|$)', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^(おわりに|エピローグ|Epilogue|Conclusion|付録|Appendix|索引|Index)(?:\s+|$)', re.IGNORECASE | re.MULTILINE),
    ]

    detected = []
    seen_pages = set()

    for page_idx in range(len(reader.pages)):
        try:
            page_text = reader.pages[page_idx].extract_text() or ""
            if not page_text.strip():
                continue

            lines = page_text.splitlines()
            for line in lines[:15]:
                line = line.strip()
                if not line or len(line) < 2:
                    continue

                for pattern in top_level_patterns:
                    match = pattern.search(line)
                    if match:
                        physical_page = page_idx + 1
                        if physical_page not in seen_pages:
                            title = match.group(1)
                            detected.append(TocEntry(
                                title=title[:60],
                                printed_page=physical_page,
                                is_chapter=True,
                                physical_page=physical_page,
                            ))
                            seen_pages.add(physical_page)
                        break

        except Exception:
            continue

    return sorted(detected, key=lambda e: e.physical_page)


def uniform_fallback_split(
    reader: PdfReader,
    output_dir: Path,
    total_size_mb: float,
    max_size_mb: float,
) -> list[dict]:
    """
    目次解析に失敗した場合、ファイルサイズから分割数を計算して均等ページ分割。
    """
    total_pages = len(reader.pages)
    num_parts = max(1, math.ceil(total_size_mb / max_size_mb))
    pages_per_part = max(1, math.ceil(total_pages / num_parts))

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for i in range(num_parts):
        start = i * pages_per_part + 1
        end = min((i + 1) * pages_per_part, total_pages)
        if start > total_pages:
            break
        writer = PdfWriter()
        for p in range(start - 1, end):
            writer.add_page(reader.pages[p])
        fname = f"part{i+1:02d}_p{start}-{end}.pdf"
        out_path = output_dir / fname
        with open(out_path, "wb") as f:
            writer.write(f)
        outputs.append({
            "path": str(out_path),
            "title": f"part{i+1}",
            "start": start,
            "end": end,
            "size_mb": out_path.stat().st_size / (1024 ** 2),
        })

    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", help="対象PDFファイルのパス")
    parser.add_argument("--max-size-mb", type=float, default=20, help="最大ファイルサイズ (MB)")
    parser.add_argument("--lang", default="jpn+eng", help="ocrmypdf の言語指定")
    parser.add_argument("--force-ocr", action="store_true", help="既存のOCR済みファイルを無視して再実行")
    parser.add_argument("--chapters-json", help="章のタイトルと開始物理ページを指定するJSONファイルのパス")
    args = parser.parse_args()

    input_pdf = Path(args.input_pdf).resolve()
    if not input_pdf.exists():
        print(f"Error: {input_pdf} not found", file=sys.stderr)
        sys.exit(1)


    if not pdf_utils.ensure_ocrmypdf_installed():
        print("Error: ocrmypdf command not found. Run: brew install ocrmypdf", file=sys.stderr)
        sys.exit(1)

    stem = input_pdf.stem
    output_base = input_pdf.parent / "output" / stem
    ocr_pdf = output_base / f"{stem}_ocr.pdf"
    chapters_dir = output_base / "chapters"

    if not pdf_utils.run_ocr(input_pdf, ocr_pdf, args.lang, args.force_ocr, step_label="[1/3]"):
        sys.exit(1)

    print("[2/3] 目次解析・分割中...", file=sys.stderr)
    reader = PdfReader(str(ocr_pdf))
    total_pages = len(reader.pages)
    total_size_mb = ocr_pdf.stat().st_size / (1024 ** 2)

    fallback_used = False
    fallback_type = None

    if args.chapters_json:
        print(f"  指定されたJSONファイルから章境界をロード中: {args.chapters_json}", file=sys.stderr)
        with open(args.chapters_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        boundaries = []
        for item in data:
            boundaries.append(TocEntry(
                title=item["title"],
                printed_page=item["page"],
                is_chapter=True,
                physical_page=item["page"]
            ))
        
        # 物理ページでソート
        boundaries = sorted(boundaries, key=lambda e: e.physical_page)
        
        outputs = split_by_boundaries(reader, boundaries, chapters_dir)
        print("[3/3] 20MB超の再分割中...", file=sys.stderr)
        resplit_outputs = []
        for i, chapter_info in enumerate(outputs, start=1):
            prefix = f"{i:02d}"
            resplit_outputs.extend(
                resplit_oversized(reader, chapter_info, boundaries, chapters_dir, args.max_size_mb, prefix)
            )
        outputs = resplit_outputs
        
        # 互換性のための変数定義とレポート用
        toc_page_indices = []
        entries = boundaries
        chapter_entries = boundaries
        offset = 0
        fallback_used = False
        fallback_type = "explicit_json"

    else:
        toc_page_indices = find_toc_pages(reader)
        entries = parse_toc_entries(reader, toc_page_indices) if toc_page_indices else []
        chapter_entries = [e for e in entries if e.is_chapter]
        offset = compute_offset(reader, entries) if chapter_entries else None
        boundaries = build_chapter_boundaries(entries, offset, total_pages) if offset is not None else []

        if len(boundaries) < 2:
            print("  目次解析に失敗。キーワード検出を試行中...", file=sys.stderr)

            detected_chapters = None

            if chapter_entries:
                detected_chapters = detect_chapters_by_toc_titles(reader, chapter_entries)
                if len(detected_chapters) >= 2:
                    print(f"  {len(detected_chapters)}個の章を検出。目次章名ベース分割を実行。", file=sys.stderr)
                    fallback_type = "toc_title_detection"

            if not detected_chapters or len(detected_chapters) < 2:
                print("  本文内の章番号・キーワードを検出中...", file=sys.stderr)
                detected_chapters = detect_chapters_by_keywords(reader)
                if len(detected_chapters) >= 2:
                    print(f"  {len(detected_chapters)}個の章キーワードを検出。キーワードベース分割を実行。", file=sys.stderr)
                    fallback_type = "keyword_detection"

            if detected_chapters and len(detected_chapters) >= 2:
                fallback_used = True
                outputs = split_by_boundaries(reader, detected_chapters, chapters_dir)
                print("[3/3] 20MB超の再分割中...", file=sys.stderr)
                resplit_outputs = []
                for i, chapter_info in enumerate(outputs, start=1):
                    prefix = f"{i:02d}"
                    resplit_outputs.extend(
                        resplit_oversized(reader, chapter_info, detected_chapters, chapters_dir, args.max_size_mb, prefix)
                    )
                outputs = resplit_outputs
            else:
                print("  キーワード検出失敗。均等ページ分割にフォールバック。", file=sys.stderr)
                fallback_used = True
                fallback_type = "uniform_split"
                outputs = uniform_fallback_split(reader, chapters_dir, total_size_mb, args.max_size_mb)
        else:
            outputs = split_by_boundaries(reader, boundaries, chapters_dir)
            print("[3/3] 20MB超の再分割中...", file=sys.stderr)
            resplit_outputs = []
            for i, chapter_info in enumerate(outputs, start=1):
                prefix = f"{i:02d}"
                resplit_outputs.extend(
                    resplit_oversized(reader, chapter_info, entries, chapters_dir, args.max_size_mb, prefix)
                )
            outputs = resplit_outputs

    report = {
        "input_pdf": str(input_pdf),
        "ocr_pdf": str(ocr_pdf),
        "ocr_pdf_size_mb": total_size_mb,
        "total_pages": total_pages,
        "toc_pages_detected": len(toc_page_indices),
        "toc_page_indices": toc_page_indices,
        "all_entries_count": len(entries),
        "chapter_entries_count": len(chapter_entries),
        "offset": offset,
        "boundaries_count": len(boundaries),
        "fallback_used": fallback_used,
        "fallback_type": fallback_type,
        "max_size_mb": args.max_size_mb,
        "outputs": outputs,
    }

    report_path = output_base / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[完了] {len(outputs)}ファイル生成", file=sys.stderr)
    print(f"  レポート: {report_path}", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
