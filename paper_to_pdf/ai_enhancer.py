"""
ai_enhancer.py
==============
オープンソース AI モデルを使った書籍スキャン画像補正モジュール。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import cv2
import numpy as np

from utils.device import get_device
from utils.download import download_file
from utils.paths import CACHE_DIR

logger = logging.getLogger(__name__)

_TQDM_FMT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"


def _apply_tiled(
    img: np.ndarray,
    tile_fn,
    tile_size: int,
    tile_pad: int,
    out_scale: int = 1,
    desc: str = "",
) -> np.ndarray:
    from tqdm import tqdm
    h, w = img.shape[:2]
    s = out_scale
    out_h, out_w = h * s, w * s
    output = np.zeros((out_h, out_w, img.shape[2]), dtype=img.dtype)
    tiles = [(y, x) for y in range(0, h, tile_size) for x in range(0, w, tile_size)]
    with tqdm(tiles, desc=desc, unit="tile", leave=False, bar_format=_TQDM_FMT) as pbar:
        for y, x in pbar:
            y1 = max(0, y - tile_pad);  y2 = min(h, y + tile_size + tile_pad)
            x1 = max(0, x - tile_pad);  x2 = min(w, x + tile_size + tile_pad)
            out_patch = tile_fn(img[y1:y2, x1:x2])
            py1 = (y - y1) * s;  py2 = py1 + min(tile_size, h - y) * s
            px1 = (x - x1) * s;  px2 = px1 + min(tile_size, w - x) * s
            output[y * s: min(out_h, (y + tile_size) * s),
                   x * s: min(out_w, (x + tile_size) * s)] = out_patch[py1:py2, px1:px2]
    return output

def _build_rrdbnet(scale: int):  # pragma: no cover
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    def _pixel_unshuffle(x, scale):
        b, c, h, w = x.size()
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
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self, num_in_ch=3, num_out_ch=3, scale=4, num_feat=64, num_block=23, num_grow_ch=32):
            super().__init__()
            self.scale = scale
            in_ch = num_in_ch * (4 if scale == 2 else 16 if scale == 1 else 1)
            self.conv_first = nn.Conv2d(in_ch, num_feat, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(num_feat=num_feat, num_grow_ch=num_grow_ch) for _ in range(num_block)])
            self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up1  = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up2  = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_hr   = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)
        def forward(self, x):
            if self.scale == 2: x = _pixel_unshuffle(x, scale=2)
            elif self.scale == 1: x = _pixel_unshuffle(x, scale=4)
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    return RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=scale)

class _RealESRGANInferencer:  # pragma: no cover
    _TILE_SIZE = 512
    _TILE_PAD  = 10
    def __init__(self, scale: int, model_path: str):
        import torch
        self.scale = scale; self._device = get_device(); self._model = _build_rrdbnet(scale)
        state = torch.load(model_path, map_location=self._device, weights_only=True)
        params = state.get("params_ema") or state.get("params") or state
        self._model.load_state_dict(params, strict=True); self._model.eval(); self._model = self._model.to(self._device)
    def enhance(self, img_rgb: np.ndarray) -> np.ndarray:
        import torch
        img_f = img_rgb.astype(np.float32) / 255.0; h, w = img_f.shape[:2]
        if max(h, w) <= self._TILE_SIZE:
            t = torch.from_numpy(img_f).permute(2, 0, 1).unsqueeze(0).to(self._device)
            t, (ph, pw) = self._pad(t)
            with torch.no_grad(): out = self._model(t)
            out = out[:, :, : (h - ph) * self.scale, : (w - pw) * self.scale]
            out_np = out.squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
        else: out_np = self._tile_enhance(img_f)
        return (out_np * 255.0).clip(0, 255).astype(np.uint8)
    def _pad(self, t):
        import torch.nn.functional as F
        _, _, h, w = t.shape; ph = (self.scale - h % self.scale) % self.scale; pw = (self.scale - w % self.scale) % self.scale
        if ph or pw: t = F.pad(t, (0, pw, 0, ph), mode="reflect")
        return t, (ph, pw)
    def _infer_patch(self, patch: np.ndarray) -> np.ndarray:
        import torch
        s = self.scale; t = torch.from_numpy(patch).permute(2, 0, 1).unsqueeze(0).to(self._device)
        t, _ = self._pad(t)
        with torch.no_grad(): out = self._model(t)
        return out[:, :, :patch.shape[0] * s, :patch.shape[1] * s].squeeze(0).permute(1, 2, 0).clamp(0, 1).cpu().numpy()
    def _tile_enhance(self, img_f: np.ndarray) -> np.ndarray:
        return _apply_tiled(img_f, self._infer_patch, self._TILE_SIZE, self._TILE_PAD, self.scale, "Real-ESRGAN")

class BaseAIEnhancer(ABC):
    @abstractmethod
    def enhance(self, image: np.ndarray) -> np.ndarray: pass
    def name(self) -> str: return self.__class__.__name__

class RealESRGANEnhancer(BaseAIEnhancer):
    def __init__(self, scale: int = 2):
        if scale not in (2, 4): raise ValueError("scale は 2 または 4 を指定してください。")
        self.scale = scale; self._upsampler = None; self._try_load()
    _URLS = {
        2: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        4: "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x4plus.pth",
    }
    _SHA256 = {
        2: "49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb",
        4: "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
    }
    def _try_load(self) -> None:  # pragma: no cover
        try:
            model_path = CACHE_DIR / f"RealESRGAN_x{self.scale}plus.pth"
            if not model_path.exists():
                logger.info("RealESRGAN x%d モデルをダウンロード中...", self.scale)
                download_file(self._URLS[self.scale], model_path,
                              expected_sha256=self._SHA256[self.scale])
            self._upsampler = _RealESRGANInferencer(scale=self.scale, model_path=str(model_path))
        except Exception as e:
            logger.warning("RealESRGAN の読み込みに失敗しました（Lanczos にフォールバック）: %s", e)
    def enhance(self, image: np.ndarray) -> np.ndarray:
        if self._upsampler is not None:
            try: return cv2.cvtColor(self._upsampler.enhance(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)), cv2.COLOR_RGB2BGR)
            except Exception: pass
        h, w = image.shape[:2]; return cv2.resize(image, (w * self.scale, h * self.scale), interpolation=cv2.INTER_LANCZOS4)
    def name(self) -> str: return f"RealESRGAN_x{self.scale}"

class Swin2SREnhancer(BaseAIEnhancer):
    _TILE_SIZE = 128; _TILE_PAD = 8
    def __init__(self, scale: int = 2):
        if scale not in (2, 4): self.scale = 2
        self.scale = scale; self._model = None; self._processor = None; self._device = "cpu"; self._try_load()
    def _try_load(self) -> None:  # pragma: no cover
        try:
            from transformers import Swin2SRForImageSuperResolution, Swin2SRImageProcessor
            mid = f"caidas/swin2SR-classical-sr-x{self.scale}-64"
            self._processor = Swin2SRImageProcessor.from_pretrained(mid); self._model = Swin2SRForImageSuperResolution.from_pretrained(mid)
            self._model.eval(); self._device = get_device(); self._model = self._model.to(self._device)
        except Exception: pass
    def _infer_tile(self, tile_rgb: np.ndarray) -> np.ndarray:
        import torch; from PIL import Image
        pil = Image.fromarray(tile_rgb); inputs = self._processor(pil, return_tensors="pt").to(self._device)
        with torch.no_grad(): out = self._model(**inputs)
        sr = out.reconstruction.squeeze().clamp(0, 1); sr_np = (sr.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
        return sr_np[:tile_rgb.shape[0] * self.scale, :tile_rgb.shape[1] * self.scale]
    def enhance(self, image: np.ndarray) -> np.ndarray:
        if self._model is None: h, w = image.shape[:2]; return cv2.resize(image, (w * self.scale, h * self.scale), interpolation=cv2.INTER_LANCZOS4)
        try:
            out = _apply_tiled(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), self._infer_tile, self._TILE_SIZE, self._TILE_PAD, self.scale, "Swin2SR")
            return cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
        except Exception: h, w = image.shape[:2]; return cv2.resize(image, (w * self.scale, h * self.scale), interpolation=cv2.INTER_LANCZOS4)
    def name(self) -> str: return f"Swin2SR_x{self.scale}"

def _build_docres_unet():  # pragma: no cover
    import torch; import torch.nn as nn
    class DoubleConv(nn.Module):
        def __init__(self, in_ch, out_ch):
            super().__init__()
            self.conv = nn.Sequential(nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(True), nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(True))
        def forward(self, x): return self.conv(x)
    class UNet(nn.Module):
        def __init__(self):
            super().__init__(); self.inc = DoubleConv(3, 64); self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(64, 128))
            self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(128, 256)); self.down3 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(256, 512))
            self.up1 = nn.ConvTranspose2d(512, 256, 2, stride=2); self.upc1 = DoubleConv(512, 256)
            self.up2 = nn.ConvTranspose2d(256, 128, 2, stride=2); self.upc2 = DoubleConv(256, 128)
            self.up3 = nn.ConvTranspose2d(128, 64, 2, stride=2); self.upc3 = DoubleConv(128, 64); self.outc = nn.Conv2d(64, 3, 1); self.sigmoid = nn.Sigmoid()
        def forward(self, x):
            x1 = self.inc(x); x2 = self.down1(x1); x3 = self.down2(x2); x4 = self.down3(x3)
            x = self.up1(x4); x = self.upc1(torch.cat([x, x3], 1)); x = self.up2(x); x = self.upc2(torch.cat([x, x2], 1))
            x = self.up3(x); x = self.upc3(torch.cat([x, x1], 1)); return self.sigmoid(self.outc(x))
    return UNet()

class DocResEnhancer(BaseAIEnhancer):
    def __init__(self, scale: int = 1):
        self.scale = scale; self._model = None; self._device = "cpu"; self._try_load()
    _MODEL_URL = ""  # DocRes の公開モデルは未提供。手動でキャッシュディレクトリに配置してください。
    def _try_load(self) -> None:  # pragma: no cover
        try:
            import torch; model_path = CACHE_DIR / "docres_unet.pth"
            if not model_path.exists():
                if not self._MODEL_URL:
                    logger.warning("DocResEnhancer: モデルファイルが見つかりません (%s)。remove_shadow にフォールバックします。", model_path)
                    return
                logger.info("DocRes モデルをダウンロード中...")
                download_file(self._MODEL_URL, model_path)
            self._device = get_device(); self._model = _build_docres_unet()
            if model_path.exists(): self._model.load_state_dict(torch.load(str(model_path), map_location=self._device, weights_only=True))
            self._model.eval(); self._model = self._model.to(self._device)
        except Exception as e:
            logger.warning("DocResEnhancer の読み込みに失敗しました（remove_shadow にフォールバック）: %s", e)
    def enhance(self, image: np.ndarray) -> np.ndarray:
        if self._model is None:
            from image_processor import remove_shadow
            return remove_shadow(image, strength=1.0)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB); img_f = rgb.astype(np.float32) / 255.0
        out = _apply_tiled(img_f, self._infer_patch, 512, 16, 1, "DocRes")
        return (out * 255.0).clip(0, 255).astype(np.uint8)
    def _infer_patch(self, patch: np.ndarray) -> np.ndarray:
        import torch; import torch.nn.functional as F
        ph, pw = (16 - patch.shape[0] % 16) % 16, (16 - patch.shape[1] % 16) % 16
        t = torch.from_numpy(patch).permute(2, 0, 1).unsqueeze(0).to(self._device)
        if ph or pw: t = F.pad(t, (0, pw, 0, ph), mode="reflect")
        with torch.no_grad(): out = self._model(t)
        return out[:, :, :patch.shape[0], :patch.shape[1]].squeeze(0).permute(1, 2, 0).cpu().numpy()

def create_enhancer(backend: str, scale: int = 2) -> BaseAIEnhancer:
    if backend == "realesrgan": return RealESRGANEnhancer(scale=scale)
    elif backend == "swin2sr": return Swin2SREnhancer(scale=scale)
    elif backend == "docres": return DocResEnhancer(scale=scale)
    else: raise ValueError(f"Unknown backend: {backend}")
