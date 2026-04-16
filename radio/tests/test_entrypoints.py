import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401


class EntrypointTest(unittest.TestCase):
    def test_package_main_invokes_cli_main(self):
        with patch("nhk_radio.cli.main") as main_mock:
            runpy.run_module("nhk_radio", run_name="__main__")
        main_mock.assert_called_once_with()

    def test_wrapper_main_function_invokes_cli_main(self):
        import nhk_radio_dl

        with patch("nhk_radio.cli.main") as main_mock:
            nhk_radio_dl.main()
        main_mock.assert_called_once_with()

    def test_wrapper_script_invokes_cli_main(self):
        wrapper_path = Path(__file__).resolve().parents[1] / "nhk_radio_dl.py"
        with patch("nhk_radio.cli.main") as main_mock:
            runpy.run_path(str(wrapper_path), run_name="__main__")
        main_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
