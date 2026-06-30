---
name: pdf-chapter-splitter
description: Split a PDF file into chapters based on page ranges. Use when the user needs to break a large PDF (like a Kindle export) into smaller, manageable chapter files. Auto-clears the output directory before processing.
---

# PDF Chapter Splitter

This skill helps you split a PDF file into multiple chapters by defining page ranges.

## Workflow

1.  **Identify PDF**: Locate the source PDF file and determine the page ranges for each chapter.
2.  **Configure Script**: Open `scripts/split_pdf.py` and edit the `__main__` block to define:
    -   `input_pdf`: Path to your source PDF.
    -   `output_directory`: Path where splits will be saved (e.g., `./chapters`).
    -   `chapters`: A list of `[chapter_name, start_page, end_page]`.
3.  **Execute**: Run the script using Python.

## Important Note on Directory Clearing

The script is designed to **auto-clear** the `output_directory` before generating new splits. Any existing files in that folder will be deleted.

## Usage Example

```python
chapters = [
    ["ch_01", 1, 20],
    ["ch_02", 21, 50],
]
input_pdf = "./my_book.pdf"
output_directory = "./chapters"
```

Running the script will delete `./chapters`, recreate it, and save `ch_01.pdf` and `ch_02.pdf` inside.
