"""PDF combination and page extraction utilities for admit cards."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader, PdfWriter
from rich.console import Console

console = Console()


def combine_page1_only(pdf_files: List[Path], output_file: Path) -> int:
    """Merges only the first page (Page 1) of each admit card into a single PDF."""
    writer = PdfWriter()
    page_count = 0

    for pdf_path in pdf_files:
        try:
            reader = PdfReader(str(pdf_path))
            if len(reader.pages) > 0:
                writer.add_page(reader.pages[0])
                page_count += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {pdf_path.name}: {e}[/yellow]")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "wb") as f:
        writer.write(f)

    return page_count


def combine_all_pages_together(pdf_files: List[Path], output_file: Path) -> int:
    """Merges all pages of each admit card together in order into a single PDF."""
    writer = PdfWriter()
    page_count = 0

    for pdf_path in pdf_files:
        try:
            reader = PdfReader(str(pdf_path))
            for page in reader.pages:
                writer.add_page(page)
                page_count += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {pdf_path.name}: {e}[/yellow]")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "wb") as f:
        writer.write(f)

    return page_count


def combine_separate_pages(
    pdf_files: List[Path],
    page1_output: Path,
    page2_output: Path,
) -> Tuple[int, int]:
    """Extracts Page 1 into one combined PDF and Page 2 into another separate combined PDF."""
    writer_p1 = PdfWriter()
    writer_p2 = PdfWriter()
    p1_count = 0
    p2_count = 0

    for pdf_path in pdf_files:
        try:
            reader = PdfReader(str(pdf_path))
            num_pages = len(reader.pages)
            if num_pages >= 1:
                writer_p1.add_page(reader.pages[0])
                p1_count += 1
            if num_pages >= 2:
                writer_p2.add_page(reader.pages[1])
                p2_count += 1
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read {pdf_path.name}: {e}[/yellow]")

    page1_output.parent.mkdir(parents=True, exist_ok=True)
    page2_output.parent.mkdir(parents=True, exist_ok=True)

    with open(page1_output, "wb") as f:
        writer_p1.write(f)

    if p2_count > 0:
        with open(page2_output, "wb") as f:
            writer_p2.write(f)

    return p1_count, p2_count
