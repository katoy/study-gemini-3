#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#     "myocr-kit==0.1.1",
# ]
# ///
"""
MyOCR (robbyzhaox/myocr) で画像を OCR し、ページごとのテキストと処理時間を書き出す PoC。

--rec-model を省略すると MyOCR 標準の認識モデル (~/.MyOCR/models/rec.onnx) を使う。
指定した場合は、その ONNX のメタデータ `character` を文字辞書として認識処理を差し替える。
"""

import argparse
import json
import time
from pathlib import Path

import onnxruntime as ort
from myocr.base import Predictor
from myocr.config import MODEL_PATH
from myocr.modeling.model import ModelZoo
from myocr.processors import (
    TextDetectionProcessor,
    TextDirectionProcessor,
    TextRecognitionProcessor,
)
from myocr.processors.base import LabelTranslator
from myocr.types import OCRResult

DEVICE = "cpu"


class DictRecognitionProcessor(TextRecognitionProcessor):
    """文字辞書だけを差し替えた認識処理（前処理と CTC デコードは MyOCR 標準のまま）。"""

    def __init__(self, characters: list[str]) -> None:
        super().__init__()
        self.translator = LabelTranslator("".join(characters))


def load_characters(rec_model: Path) -> list[str]:
    """PaddleOCR 系 ONNX のメタデータから文字辞書を取り出す。"""
    meta = ort.InferenceSession(str(rec_model)).get_modelmeta().custom_metadata_map
    characters = meta["character"].splitlines()
    # LabelTranslator は 1 文字ずつ添字で引くため、複数文字のエントリがあると位置がずれる
    multi = [c for c in characters if len(c) != 1]
    if multi:
        raise ValueError(f"1 文字でない辞書エントリがあります: {multi[:5]}")
    return characters


def build_predictors(rec_model: Path | None) -> tuple[Predictor, Predictor, Predictor]:
    """検出・向き判定・認識の Predictor を組み立てる。"""
    det = ModelZoo.load_model("onnx", MODEL_PATH + "dbnet++.onnx", DEVICE)
    cls = ModelZoo.load_model("onnx", MODEL_PATH + "cls.onnx", DEVICE)
    if rec_model is None:
        rec = ModelZoo.load_model("onnx", MODEL_PATH + "rec.onnx", DEVICE)
        rec_processor = TextRecognitionProcessor()
    else:
        rec = ModelZoo.load_model("onnx", str(rec_model), DEVICE)
        rec_processor = DictRecognitionProcessor(load_characters(rec_model))
    return (
        Predictor(det, TextDetectionProcessor(det.device)),
        Predictor(cls, TextDirectionProcessor()),
        Predictor(rec, rec_processor),
    )


def ocr_image(predictors: tuple[Predictor, Predictor, Predictor], image_path: Path) -> str:
    """1 枚の画像を OCR し、上から順に並べたテキストを返す（CommonOCRPipeline.process と同じ流れ）。"""
    import cv2

    det, cls, rec = predictors
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR_RGB)
    detected = det.predict(image)
    texts = []
    if detected[1]:
        texts = rec.predict(cls(detected))
    result = OCRResult.build(image, texts, 0.0)
    regions = sorted(
        result.regions,
        key=lambda r: (r.bounding_shape.points[0].y, r.bounding_shape.points[0].x),
    )
    return "\n".join(r.text for r in regions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="OCR する画像ファイル")
    parser.add_argument("--out", type=Path, required=True, help="結果の出力ディレクトリ")
    parser.add_argument("--rec-model", type=Path, help="差し替える認識モデル (ONNX)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    predictors = build_predictors(args.rec_model)
    timings: dict[str, float] = {}
    for image_path in args.images:
        start = time.perf_counter()
        text = ocr_image(predictors, image_path)
        timings[image_path.stem] = time.perf_counter() - start
        (args.out / f"{image_path.stem}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"{image_path.name}: {timings[image_path.stem]:.2f}s")
    (args.out / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
