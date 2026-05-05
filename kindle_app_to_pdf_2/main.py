import argparse
import os
import time
from datetime import datetime
from typing import List, Optional

import img2pdf  # type: ignore
import pyautogui as py  # type: ignore

# Constants
DEFAULT_OUTPUT_DIR = "KindleScreenshots"
DEFAULT_PAGE_TURN_WAIT = 1.0  # Seconds to wait after turning a page
DEFAULT_JPEG_QUALITY = 80  # JPEG quality (0-100)
START_DELAY = 5  # Seconds to wait before starting capture


class KindleCapturer:
    """Handles capturing Kindle screenshots and converting them to PDF."""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        page_turn_wait: float = DEFAULT_PAGE_TURN_WAIT,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    ):
        self.output_dir = output_dir
        self.page_turn_wait = page_turn_wait
        self.jpeg_quality = jpeg_quality

    def _ensure_output_dir(self) -> None:
        """Creates the output directory if it doesn't exist."""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created directory: {self.output_dir}")

    def capture_pages(self, total_pages: int, direction: str) -> None:
        """
        Captures the specified number of pages by simulating key presses.

        Args:
            total_pages: Number of pages to capture.
            direction: 'left' or 'right' for page turning.
        """
        self._ensure_output_dir()
        turn_key = "left" if direction == "left" else "right"

        print(f"Starting capture: {total_pages} pages, direction: {direction}")
        print(f"Please activate the Kindle app. Starting in {START_DELAY} seconds...")
        time.sleep(START_DELAY)

        try:
            for i in range(1, total_pages + 1):
                # Capture screenshot
                screenshot = py.screenshot()

                # Generate file path (zero-padded 4-digit sequence)
                file_path = os.path.join(self.output_dir, f"page_{i:04d}.jpg")

                # Convert to RGB and save as JPEG
                screenshot.convert("RGB").save(
                    file_path, "JPEG", quality=self.jpeg_quality
                )
                print(f"Captured: {i} / {total_pages}")

                # Simulate page turn
                py.press(turn_key)

                # Wait for page to load
                time.sleep(self.page_turn_wait)

            print("\nCapture completed successfully.")

        except KeyboardInterrupt:
            print("\nCapture interrupted by user. Proceeding to generate PDF with current images.")
        except Exception as e:
            print(f"\nAn error occurred during capture: {e}")

    def create_pdf(self, output_pdf_name: Optional[str] = None) -> None:
        """
        Converts the captured JPEG images in the output directory to a single PDF.

        Args:
            output_pdf_name: Name of the output PDF file. If None, generates one based on timestamp.
        """
        if output_pdf_name is None:
            output_pdf_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        print(f"\nGenerating PDF: {output_pdf_name}")

        try:
            # Gather and sort JPEG files
            image_paths: List[str] = []
            if not os.path.exists(self.output_dir):
                print(f"Error: Directory '{self.output_dir}' does not exist.")
                return

            file_names = sorted(os.listdir(self.output_dir))
            for file_name in file_names:
                if file_name.lower().endswith(".jpg"):
                    image_paths.append(os.path.join(self.output_dir, file_name))

            if not image_paths:
                print("No images found to convert.")
                return

            # Convert to PDF
            with open(output_pdf_name, "wb") as f:
                f.write(img2pdf.convert(image_paths))

            print(f"PDF successfully created: {output_pdf_name}")

        except Exception as e:
            print(f"Failed to create PDF: {e}")


def parse_arguments() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Capture Kindle pages and convert to PDF.")
    parser.add_argument(
        "--direction",
        choices=["left", "right"],
        default="right",
        help="Page turn direction (default: right)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=200,
        help="Number of pages to capture (default: 200)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Custom name for the output PDF file",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for the script."""
    args = parse_arguments()

    capturer = KindleCapturer()
    capturer.capture_pages(total_pages=args.pages, direction=args.direction)
    capturer.create_pdf(output_pdf_name=args.output)


if __name__ == "__main__":
    main()
