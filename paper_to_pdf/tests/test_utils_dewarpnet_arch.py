"""
utils/dewarpnet_arch.py のテスト。
"""
import torch
from utils.dewarpnet_arch import (
    convert_state_dict,
    UnetGenerator,
    DnetCCNL,
    _add_coord_channels
)

def test_convert_state_dict():
    sd = {"module.conv1.weight": 1, "conv2.weight": 2}
    new_sd = convert_state_dict(sd)
    assert "conv1.weight" in new_sd
    assert "conv2.weight" in new_sd
    assert "module.conv1.weight" not in new_sd

def test_unet_generator_and_blocks():
    # 最小構成で forward を通す
    model = UnetGenerator(input_nc=3, output_nc=3, num_downs=7, ngf=4, use_dropout=True)
    model.eval()
    x = torch.zeros((1, 3, 128, 128))
    with torch.no_grad():
        out = model(x)
    assert out.shape == (1, 3, 128, 128)

def test_dnet_ccnl_and_components():
    # 入力サイズを 128x128 に拡大してプーリングエラーを回避
    model = DnetCCNL(img_size=128, in_channels=3, out_channels=2, filters=4)
    model.eval()
    x = torch.zeros((1, 3, 128, 128))
    with torch.no_grad():
        out = model(x)
    assert out.dim() == 4
    assert out.shape[1] == 2

def test_add_coord_channels():
    x = torch.zeros((1, 3, 8, 8))
    out = _add_coord_channels(x)
    assert out.shape == (1, 5, 8, 8)
    assert float(out[0, 3, 0, 0]) == -1.0
    assert float(out[0, 3, -1, -1]) == 1.0
