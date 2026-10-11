import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.append(str(Path(__file__).parent.parent / "scripts"))

import pdf_utils


@pytest.fixture
def ndlocr_dir(tmp_path, monkeypatch):
    """ocr.py を置いたダミーの ndlocr-lite clone 先を作り、環境変数に設定する。"""
    (tmp_path / "ndlocr" / "src").mkdir(parents=True)
    (tmp_path / "ndlocr" / "src" / "ocr.py").write_text("")
    monkeypatch.setenv(pdf_utils.NDLOCR_DIR_ENV, str(tmp_path / "ndlocr"))
    return tmp_path / "ndlocr"


def test_get_ndlocr_dir(ndlocr_dir, monkeypatch):
    assert pdf_utils.get_ndlocr_dir() == ndlocr_dir
    monkeypatch.delenv(pdf_utils.NDLOCR_DIR_ENV)
    assert pdf_utils.get_ndlocr_dir() is None


def test_ensure_ocr_engine_available(ndlocr_dir, monkeypatch):
    with patch("shutil.which", return_value="/usr/bin/uv"):
        assert pdf_utils.ensure_ocr_engine_available("ndlocr") is True
    # uv がない
    with patch("shutil.which", return_value=None):
        assert pdf_utils.ensure_ocr_engine_available("ndlocr") is False
        assert pdf_utils.ensure_ocr_engine_available("tesseract") is False
    with patch("shutil.which", return_value="/usr/bin/x"):
        assert pdf_utils.ensure_ocr_engine_available("tesseract") is True
        # ocr.py がない
        (ndlocr_dir / "src" / "ocr.py").unlink()
        assert pdf_utils.ensure_ocr_engine_available("ndlocr") is False
        # 環境変数が未設定
        monkeypatch.delenv(pdf_utils.NDLOCR_DIR_ENV)
        assert pdf_utils.ensure_ocr_engine_available("ndlocr") is False


def test_build_ocr_command(ndlocr_dir, tmp_path, monkeypatch):
    in_pdf, out_pdf, work = tmp_path / "in.pdf", tmp_path / "out.pdf", tmp_path / "work"
    cmd = pdf_utils.build_ocr_command("ndlocr", in_pdf, out_pdf, "jpn", work)
    assert cmd[:2] == ["uv", "run"]
    assert str(ndlocr_dir / "requirements.txt") in cmd
    assert str(ndlocr_dir / "src" / "ocr.py") in cmd
    assert cmd[cmd.index("--sourcepdf") + 1] == str(in_pdf)
    assert cmd[cmd.index("--pdf-output") + 1] == str(out_pdf)
    assert cmd[cmd.index("--output") + 1] == str(work)

    cmd = pdf_utils.build_ocr_command("tesseract", in_pdf, out_pdf, "jpn_vert", work)
    assert cmd == ["ocrmypdf", "--skip-text", "-l", "jpn_vert", str(in_pdf), str(out_pdf)]

    monkeypatch.delenv(pdf_utils.NDLOCR_DIR_ENV)
    with pytest.raises(ValueError):
        pdf_utils.build_ocr_command("ndlocr", in_pdf, out_pdf, "jpn", work)


def test_run_ocr_skip_existing(tmp_path):
    out_pdf = tmp_path / "out.pdf"
    out_pdf.write_bytes(b"%PDF")
    with patch("subprocess.run") as mock_run:
        assert pdf_utils.run_ocr(tmp_path / "in.pdf", out_pdf) is True
    mock_run.assert_not_called()


def test_run_ocr_success(ndlocr_dir, tmp_path):
    in_pdf, out_pdf = tmp_path / "in.pdf", tmp_path / "sub" / "out.pdf"
    in_pdf.write_bytes(b"%PDF")

    def fake_run(cmd, **kwargs):
        Path(cmd[cmd.index("--pdf-output") + 1]).write_bytes(b"%PDF")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("subprocess.run", side_effect=fake_run) as mock_run:
        assert pdf_utils.run_ocr(in_pdf, out_pdf, force=True, step_label="[1/3]") is True
    assert mock_run.call_args.kwargs["timeout"] == pdf_utils.OCR_TIMEOUT_SEC
    assert out_pdf.exists()


def test_run_ocr_no_output(ndlocr_dir, tmp_path):
    in_pdf = tmp_path / "in.pdf"
    in_pdf.write_bytes(b"%PDF")
    with patch("subprocess.run"):
        assert pdf_utils.run_ocr(in_pdf, tmp_path / "out.pdf", engine="tesseract") is False


def test_run_ocr_failure(ndlocr_dir, tmp_path):
    in_pdf = tmp_path / "in.pdf"
    in_pdf.write_bytes(b"%PDF")
    error = subprocess.CalledProcessError(1, "uv", stderr=b"boom")
    with patch("subprocess.run", side_effect=error):
        assert pdf_utils.run_ocr(in_pdf, tmp_path / "out.pdf") is False
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("uv", 1)):
        assert pdf_utils.run_ocr(in_pdf, tmp_path / "out.pdf") is False
