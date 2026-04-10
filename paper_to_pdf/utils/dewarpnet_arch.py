"""
utils/dewarpnet_arch.py
=======================
DewarpNet のモデルアーキテクチャ定義。
"""

from __future__ import annotations

import functools
from collections import OrderedDict

import torch
import torch.nn as nn


def convert_state_dict(state_dict: dict) -> OrderedDict:
    new = OrderedDict()
    for k, v in state_dict.items():
        new[k[7:] if k.startswith("module.") else k] = v
    return new


class UnetSkipConnectionBlock(nn.Module):
    def __init__(self, outer_nc, inner_nc, input_nc=None,
                 submodule=None, outermost=False, innermost=False,
                 norm_layer=nn.BatchNorm2d, use_dropout=False):
        super().__init__()
        self.outermost = outermost
        use_bias = (norm_layer == nn.InstanceNorm2d or (isinstance(norm_layer, functools.partial) and norm_layer.func == nn.InstanceNorm2d))
        if input_nc is None:
            input_nc = outer_nc
        downconv = nn.Conv2d(input_nc, inner_nc, 4, 2, 1, bias=use_bias)
        downrelu = nn.LeakyReLU(0.2, True)
        downnorm = norm_layer(inner_nc)
        uprelu = nn.ReLU(True)
        upnorm = norm_layer(outer_nc)
        if outermost:
            upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, 4, 2, 1)
            model  = [downconv] + [submodule] + [uprelu, upconv, nn.Tanh()]
        elif innermost:
            upconv = nn.ConvTranspose2d(inner_nc, outer_nc, 4, 2, 1, bias=use_bias)
            model  = [downrelu, downconv, uprelu, upconv, upnorm]
        else:
            upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, 4, 2, 1, bias=use_bias)
            model  = [downrelu, downconv, downnorm, submodule, uprelu, upconv, upnorm]
            if use_dropout:
                model += [nn.Dropout(0.5)]
        self.model = nn.Sequential(*model)
    def forward(self, x):
        if self.outermost:
            return self.model(x)
        return torch.cat([x, self.model(x)], 1)


class UnetGenerator(nn.Module):
    def __init__(self, input_nc: int, output_nc: int, num_downs: int, ngf: int = 64, norm_layer=nn.BatchNorm2d, use_dropout: bool = False):
        super().__init__()
        block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, submodule=None, norm_layer=norm_layer, innermost=True)
        for _ in range(num_downs - 5):
            block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, submodule=block, norm_layer=norm_layer, use_dropout=use_dropout)
        block = UnetSkipConnectionBlock(ngf * 4, ngf * 8, submodule=block, norm_layer=norm_layer)
        block = UnetSkipConnectionBlock(ngf * 2, ngf * 4, submodule=block, norm_layer=norm_layer)
        block = UnetSkipConnectionBlock(ngf, ngf * 2, submodule=block, norm_layer=norm_layer)
        self.model = UnetSkipConnectionBlock(output_nc, ngf, input_nc=input_nc, submodule=block, outermost=True, norm_layer=norm_layer)
    def forward(self, x): return self.model(x)


def _add_coord_channels(t: torch.Tensor) -> torch.Tensor:
    n, c, h, w = t.size()
    rows = torch.linspace(-1, 1, h, device=t.device).view(h, 1).expand(h, w)
    cols = torch.linspace(-1, 1, w, device=t.device).view(1, w).expand(h, w)
    rows = rows.unsqueeze(0).unsqueeze(0).expand(n, 1, h, w)
    cols = cols.unsqueeze(0).unsqueeze(0).expand(n, 1, h, w)
    return torch.cat([t, rows, cols], dim=1)


class _DenseBlockEncoder(nn.Module):
    def __init__(self, n_ch, n_convs):
        super().__init__()
        self.layers = nn.ModuleList([nn.Sequential(nn.BatchNorm2d(n_ch), nn.ReLU(False), nn.Conv2d(n_ch, n_ch, 3, padding=1, bias=False)) for _ in range(n_convs)])
    def forward(self, x):
        outs = []
        for i, layer in enumerate(self.layers):
            inp = sum(outs) if i > 0 else x
            outs.append(layer(inp))
        return outs[-1]


class _DenseBlockDecoder(nn.Module):
    def __init__(self, n_ch, n_convs):
        super().__init__()
        self.layers = nn.ModuleList([nn.Sequential(nn.BatchNorm2d(n_ch), nn.ReLU(False), nn.ConvTranspose2d(n_ch, n_ch, 3, padding=1, bias=False)) for _ in range(n_convs)])
    def forward(self, x):
        outs = []
        for i, layer in enumerate(self.layers):
            inp = sum(outs) if i > 0 else x
            outs.append(layer(inp))
        return outs[-1]


class _DenseTransEnc(nn.Module):
    def __init__(self, in_ch, out_ch, mp):
        super().__init__()
        self.main = nn.Sequential(nn.BatchNorm2d(in_ch), nn.LeakyReLU(0.2, False), nn.Conv2d(in_ch, out_ch, 1, bias=False), nn.MaxPool2d(mp))
    def forward(self, x): return self.main(x)


class _DenseTransDec(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.main = nn.Sequential(nn.BatchNorm2d(in_ch), nn.ReLU(False), nn.ConvTranspose2d(in_ch, out_ch, 4, stride=2, padding=1, bias=False))
    def forward(self, x): return self.main(x)


class _WaspDenseEncoder128(nn.Module):
    def __init__(self, nc, ndf, ndim):
        super().__init__()
        self.ndim = ndim
        self.main = nn.Sequential(
            nn.BatchNorm2d(nc), nn.ReLU(True), nn.Conv2d(nc, ndf, 4, stride=2, padding=1),
            _DenseBlockEncoder(ndf, 6), _DenseTransEnc(ndf, ndf*2, 2), _DenseBlockEncoder(ndf*2, 12), _DenseTransEnc(ndf*2, ndf*4, 2),
            _DenseBlockEncoder(ndf*4, 16), _DenseTransEnc(ndf*4, ndf*8, 2), _DenseBlockEncoder(ndf*8, 16), _DenseTransEnc(ndf*8, ndf*8, 2),
            _DenseBlockEncoder(ndf*8, 16), _DenseTransEnc(ndf*8, ndim, 4), nn.Tanh()
        )
    def forward(self, x):
        return self.main(_add_coord_channels(x)).view(-1, self.ndim)


class _WaspDenseDecoder128(nn.Module):
    def __init__(self, nz, nc, ngf):
        super().__init__()
        self.main = nn.Sequential(
            nn.BatchNorm2d(nz), nn.ReLU(False), nn.ConvTranspose2d(nz, ngf*8, 4, 1, 0, bias=False),
            _DenseBlockDecoder(ngf*8, 16), _DenseTransDec(ngf*8, ngf*8), _DenseBlockDecoder(ngf*8, 16), _DenseTransDec(ngf*8, ngf*4),
            _DenseBlockDecoder(ngf*4, 12), _DenseTransDec(ngf*4, ngf*2), _DenseBlockDecoder(ngf*2, 6), _DenseTransDec(ngf*2, ngf),
            _DenseBlockDecoder(ngf, 6), _DenseTransDec(ngf, ngf), nn.BatchNorm2d(ngf), nn.ReLU(False),
            nn.ConvTranspose2d(ngf, nc, 3, stride=1, padding=1, bias=False), nn.Hardtanh()
        )
    def forward(self, x): return self.main(x)


class DnetCCNL(nn.Module):
    def __init__(self, img_size=128, in_channels=3, out_channels=2, filters=32):
        super().__init__()
        self.encoder = _WaspDenseEncoder128(nc=in_channels + 2, ndf=filters, ndim=img_size)
        self.decoder = _WaspDenseDecoder128(nz=img_size, nc=out_channels, ngf=filters)
    def forward(self, x):
        return self.decoder(self.encoder(x).unsqueeze(-1).unsqueeze(-1))
