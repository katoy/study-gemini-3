"""
ai_enhancer.py
==============
オープンソース AI モデルを使った書籍スキャン画像補正モジュール。

対応バックエンド:
  realesrgan : Real-ESRGAN による超解像・ノイズ除去
               (xinntao/Real-ESRGAN, Apache-2.0)
  swin2sr    : Swin2SR による Transformer ベース超解像
               (HuggingFace caidas/swin2SR, Apache-2.0)

インストール:
  pip install torch torchvision           # realesrgan バックエンド (Pure PyTorch)
  pip install transformers accelerate     # swin2sr バックエンド
"""

from __future__ import annotations

import logging
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from utils.device import get_device
from utils.paths import CACHE_DIR

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# RRDBNet アーキテクチャ (Pure PyTorch 実装)
# 外部ライブラリへの依存を排除するため、必要最小限の定義をここに内包する。
# 出典: xinntao/Real-ESRGAN (Apache-2.0 License)
# ──────────────────────────────────────────────

def _build_rrdbnet(scale: int):
    """
    RRDBNet (Residual in Residual Dense Block Network) を構築して返す。
    Pure PyTorch で定義し、追加ライブラリへの依存なし。
    """
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    def _pixel_unshuffle(x, scale):
        b, c, h, w = x.size()
        assert h % scale == 0 and w % scale == 0
        x = x.view(b, c, h // scale, scale, w // scale, scale)
        return x.permute(0, 1, 3, 5, 2, 4).reshape(b, c * scale * scale, h // scale, w // scale)

    class ResidualDenseBlock(nn.Module):
        def __init__(self, num_feat=64, num_grow_ch=32):
            super().__init__()
            self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
            self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, x):
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
            return x5 * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self, num_feat, num_grow_ch=32):
            super().__init__()
            self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
            self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
            self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

        def forward(self, x):
            out = self.rdb3(self.rdb2(self.rdb1(x)))
            return out * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self, num_in_ch=3, num_out_ch=3, scale=4,
                     num_feat=64, num_block=23, num_grow_ch=32):
            super().__init__()
            self.scale = scale
            in_ch = num_in_ch * (4 if scale == 2 else 16 if scale == 1 else 1)
            self.conv_first = nn.Conv2d(in_ch, num_feat, 3, 1, 1)
            self.body = nn.Sequential(
                *[RRDB(num_feat=num_feat, num_grow_ch=num_grow_ch) for _ in range(num_block)]
            )
            self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up1  = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up2  = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_hr   = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, x):
            if self.scale == 2:
                x = _pixel_unshuffle(x, scale=2)
            elif self.scale == 1:
                x = _pixel_unshuffle(x, scale=4)
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    return RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                   num_block=23, num_grow_ch=32, scale=scale)


# ──────────────────────────────────────────────
# Real-ESRGAN 推論クラス (Pure PyTorch)
# realesrgan パッケージ不要。basicsr 依存なし。
# ──────────────────────────────────────────────

class _RealESRGANInferencer:
    """
    RealESRGANer の代替実装。
    Pure PyTorch のみで動作し、外部パッケージへの依存を排除する。
    タイル推論により大きな画像の OOM を防ぐ。
    """

    _TILE_SIZE = 512
    _TILE_PAD  = 10

    def __init__(self, scale: int, model_path: str):
        import torch

        self.scale = scale
        self._device = get_device()
        self._model = _build_rrdbnet(scale)

        state = torch.load(model_path, map_location=self._device, weights_only=False)
        # Real-ESRGAN の checkpoint は params_ema / params のどちらかに格納される
        params = state.get("params_ema") or state.get("params") or state
        self._model.load_state_dict(params, strict=True)
        self._model.eval()
        self._model = self._model.to(self._device)

    def enhance(self, img_rgb: np.ndarray) -> np.ndarray:
        """RGB uint8 (H,W,3) を受け取り、超解像済み RGB uint8 を返す。"""
        import torch
        import torch.nn.functional as F

        img_f = img_rgb.astype(np.float32) / 255.0
        h, w = img_f.shape[:2]

        if max(h, w) <= self._TILE_SIZE:
            t = torch.from_numpy(img_f).permute(2, 0, 1).unsqueeze(0).to(self._device)
            t, (ph, pw) = self._pad(t)
            with torch.no_grad():
                out = self._model(t)
            # パディング分をトリム (出力はスケール倍されている)
            out = out[:, :, : (h - ph) * self.scale, : (w - pw) * self.scale]
            out_np = out.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
        else:
            out_np = self._tile_enhance(img_f)

        return (out_np * 255.0).clip(0, 255).astype(np.uint8)

    def _pad(self, t):
        """scale の倍数になるよう右端・下端をパディングする。"""
        import torch.nn.functional as F
        _, _, h, w = t.shape
        ph = (self.scale - h % self.scale) % self.scale
        pw = (self.scale - w % self.scale) % self.scale
        if ph or pw:
            t = F.pad(t, (0, pw, 0, ph), mode="reflect")
        return t, (ph, pw)

    def _tile_enhance(self, img_f: np.ndarray) -> np.ndarray:
        """タイル分割して推論し、結果を結合する。"""
        import torch

        s = self.scale
        pad = self._TILE_PAD
        tile = self._TILE_SIZE
        h, w = img_f.shape[:2]

        out_h, out_w = h * s, w * s
        output = np.zeros((out_h, out_w, 3), dtype=np.float32)

        for y in range(0, h, tile):
            for x in range(0, w, tile):
                y1 = max(0, y - pad);  y2 = min(h, y + tile + pad)
                x1 = max(0, x - pad);  x2 = min(w, x + tile + pad)
                patch = img_f[y1:y2, x1:x2]

                t = torch.from_numpy(patch).permute(2, 0, 1).unsqueeze(0).to(self._device)
                t, (ph, pw) = self._pad(t)
                with torch.no_grad():
                    out_p = self._model(t)
                # パディング除去
                ph_out = (patch.shape[0]) * s
                pw_out = (patch.shape[1]) * s
                out_p = out_p[:, :, :ph_out, :pw_out]
                out_p = out_p.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()

                # パッド分をトリム
                py1 = (y - y1) * s;  py2 = py1 + min(tile, h - y) * s
                px1 = (x - x1) * s;  px2 = px1 + min(tile, w - x) * s
                output[y * s: min(out_h, (y + tile) * s),
                       x * s: min(out_w, (x + tile) * s)] = out_p[py1:py2, px1:px2]

        return output


# ──────────────────────────────────────────────
# 基底クラス
# ──────────────────────────────────────────────

class BaseAIEnhancer(ABC):
    """画像補正 AI の基底クラス"""

    @abstractmethod
    def enhance(self, image: np.ndarray) -> np.ndarray:
        """BGR 画像を受け取り、補正済み BGR 画像を返す。"""

    def name(self) -> str:
        return self.__class__.__name__


# ──────────────────────────────────────────────
# Real-ESRGAN バックエンド
# ──────────────────────────────────────────────

_REALESRGAN_URLS = {
    2: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
    4: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
}


class RealESRGANEnhancer(BaseAIEnhancer):
    """
    Real-ESRGAN による超解像処理。
    realesrgan が未インストールの場合は Lanczos 補間にフォールバック。
    """

    def __init__(self, scale: int = 2):
        if scale not in (2, 4):
            raise ValueError("scale は 2 または 4 を指定してください。")
        self.scale = scale
        self._upsampler = None
        self._try_load()

    def _try_load(self) -> None:
        try:
            import torch  # noqa: F401 – torch が必要条件

            model_path = CACHE_DIR / f"RealESRGAN_x{self.scale}plus.pth"
            if not model_path.exists():
                url = _REALESRGAN_URLS[self.scale]
                logger.info(f"Real-ESRGAN モデルをダウンロード中 ({url}) ...")
                urllib.request.urlretrieve(url, model_path)
                logger.info("ダウンロード完了")

            self._upsampler = _RealESRGANInferencer(
                scale=self.scale,
                model_path=str(model_path),
            )
            logger.info(f"Real-ESRGAN x{self.scale} ロード完了")

        except ImportError:
            logger.warning(
                "torch が見つかりません。Lanczos 補間を使用します。\n"
                "  インストール: pip install torch"
            )
        except Exception as e:
            logger.warning(f"Real-ESRGAN ロード失敗: {e}. Lanczos 補間にフォールバックします。")

    def enhance(self, image: np.ndarray) -> np.ndarray:
        if self._upsampler is not None:
            try:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                out_rgb = self._upsampler.enhance(rgb)
                result = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
                logger.debug(f"Real-ESRGAN: {image.shape[:2]} → {result.shape[:2]}")
                return result
            except Exception as e:
                logger.warning(f"Real-ESRGAN 推論失敗: {e}. Lanczos にフォールバック。")

        # フォールバック
        h, w = image.shape[:2]
        return cv2.resize(image, (w * self.scale, h * self.scale),
                          interpolation=cv2.INTER_LANCZOS4)

    def name(self) -> str:
        return f"RealESRGAN_x{self.scale}"


# ──────────────────────────────────────────────
# Swin2SR バックエンド (HuggingFace Transformers)
# ──────────────────────────────────────────────

_SWIN2SR_MODELS = {
    2: "caidas/swin2SR-classical-sr-x2-64",
    4: "caidas/swin2SR-classical-sr-x4-48",
}


class Swin2SREnhancer(BaseAIEnhancer):
    """
    Swin2SR (Swin Transformer V2 for Super Resolution) による超解像処理。
    HuggingFace Transformers 経由でモデルをロードする。
    """

    def __init__(self, scale: int = 2):
        if scale not in (2, 4):
            raise ValueError("scale は 2 または 4 を指定してください。")
        self.scale = scale
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._try_load()

    def _try_load(self) -> None:
        try:
            import torch
            from transformers import Swin2SRForImageSuperResolution, Swin2SRImageProcessor

            model_id = _SWIN2SR_MODELS[self.scale]
            logger.info(f"Swin2SR モデルをロード中: {model_id} ...")

            self._processor = Swin2SRImageProcessor.from_pretrained(model_id)
            self._model = Swin2SRForImageSuperResolution.from_pretrained(model_id)
            self._model.eval()

            self._device = get_device()
            self._model = self._model.to(self._device)

            logger.info(f"Swin2SR x{self.scale} ロード完了 (device={self._device})")

        except ImportError:
            logger.warning(
                "transformers が見つかりません。Lanczos 補間を使用します。\n"
                "  インストール: pip install transformers accelerate"
            )
        except Exception as e:
            logger.warning(f"Swin2SR ロード失敗: {e}. Lanczos 補間にフォールバックします。")

    def enhance(self, image: np.ndarray) -> np.ndarray:
        if self._model is not None and self._processor is not None:
            try:
                import torch
                from PIL import Image

                # BGR → PIL RGB
                pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                inputs = self._processor(pil_img, return_tensors="pt").to(self._device)

                with torch.no_grad():
                    outputs = self._model(**inputs)

                # (1, C, H, W) → (H, W, C) numpy
                sr = outputs.reconstruction.squeeze().clamp(0, 1)
                sr_np = (sr.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
                result = cv2.cvtColor(sr_np, cv2.COLOR_RGB2BGR)
                logger.debug(f"Swin2SR: {image.shape[:2]} → {result.shape[:2]}")
                return result
            except Exception as e:
                logger.warning(f"Swin2SR 推論失敗: {e}. Lanczos にフォールバック。")

        # フォールバック
        h, w = image.shape[:2]
        return cv2.resize(image, (w * self.scale, h * self.scale),
                          interpolation=cv2.INTER_LANCZOS4)

    def name(self) -> str:
        return f"Swin2SR_x{self.scale}"


# ──────────────────────────────────────────────
# ファクトリ関数
# ──────────────────────────────────────────────

def create_enhancer(backend: str, scale: int = 2) -> BaseAIEnhancer:
    """
    バックエンド名から適切なエンハンサーを生成する。

    Args:
        backend : "realesrgan" または "swin2sr"
        scale   : 超解像の拡大倍率 (2 または 4)

    Returns:
        BaseAIEnhancer のサブクラスインスタンス
    """
    if backend == "realesrgan":
        return RealESRGANEnhancer(scale=scale)
    elif backend == "swin2sr":
        return Swin2SREnhancer(scale=scale)
    else:
        raise ValueError(
            f"不明なバックエンド: '{backend}'。"
            f" realesrgan / swin2sr のいずれかを指定してください。"
        )
