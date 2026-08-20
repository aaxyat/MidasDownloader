"""Tests for MidasDownloader parser, suggestions, target generation, and PDF merging."""

from pathlib import Path
from pypdf import PdfReader, PdfWriter
from midasdownloader.downloader import (
    StudentTarget,
    deduplicate_targets,
    extract_id_from_entrance_no,
    parse_targets_from_file,
    parse_targets_from_range,
    parse_targets_from_text,
    sanitize_file_path,
    suggest_url_template,
)
from midasdownloader.pdf_merger import (
    combine_all_pages_together,
    combine_page1_only,
    combine_separate_pages,
)


def test_sanitize_file_path():
    # Double quoted Windows path
    p1 = sanitize_file_path('"C:\\Users\\aaxyat\\Downloads\\Report.xls"')
    assert p1 == Path("C:\\Users\\aaxyat\\Downloads\\Report.xls")

    # Single quoted Windows path
    p2 = sanitize_file_path("'D:\\College\\report.xls'")
    assert p2 == Path("D:\\College\\report.xls")

    # PowerShell call prefix '&'
    p3 = sanitize_file_path('& "report_sample.xls"')
    assert p3 == Path("report_sample.xls")

    # Path object passed directly
    p4 = sanitize_file_path(Path("report_sample.xls"))
    assert p4 == Path("report_sample.xls")


def test_filename_formatting():
    target1 = StudentTarget(student_id="41819", name="Sample Student One")
    assert target1.get_filename() == "Sample_Student_One_41819.pdf"

    target2 = StudentTarget(student_id="41829", name="Sample Student Two")
    assert target2.get_filename() == "Sample_Student_Two_41829.pdf"

    target3 = StudentTarget(student_id="41819")
    assert target3.get_filename() == "admit_card_41819.pdf"


def test_entrance_no_extraction():
    assert extract_id_from_entrance_no("EN-26-41819") == "41819"
    assert extract_id_from_entrance_no("EN-26-41829") == "41829"
    assert extract_id_from_entrance_no("41626") == "41626"


def test_report_xls_parsing_with_quotes():
    sample_file = '"report_sample.xls"'
    targets = parse_targets_from_file(sample_file)
    assert len(targets) == 2
    assert targets[0].student_id == "41819"
    assert targets[0].name == "Sample Student One"
    assert targets[0].get_filename() == "Sample_Student_One_41819.pdf"


def test_comma_separated_parsing_and_deduplication():
    targets = parse_targets_from_text("41626, 41627, 41628, 41629, 41630")
    assert len(targets) == 5
    assert [t.student_id for t in targets] == ["41626", "41627", "41628", "41629", "41630"]

    targets_en = parse_targets_from_text("EN-26-41819, EN-26-41829, EN-26-41891")
    assert len(targets_en) == 3
    assert [t.student_id for t in targets_en] == ["41819", "41829", "41891"]


def test_url_template_suggestion():
    raw_url = "https://portal.university.example.edu/entrance/report/prints?entranceid=41626&levelid=3&facultyid=1&programid=30&status=&orgid=undefined&academicbatch=&verified=&isverified=&examcenterid=Y&fromdate=2026-05-27&todate=2026-08-20"
    suggested = suggest_url_template(raw_url)
    expected = "https://portal.university.example.edu/entrance/report/prints?entranceid={student_id}&levelid=3&facultyid=1&programid=30&status=&orgid=undefined&academicbatch=&verified=&isverified=&examcenterid=Y&fromdate=2026-05-27&todate=2026-08-20"
    assert suggested == expected


def test_pdf_merging(tmp_path: Path):
    pdf1_path = tmp_path / "student1.pdf"
    pdf2_path = tmp_path / "student2.pdf"

    for path in (pdf1_path, pdf2_path):
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.add_blank_page(width=595, height=842)
        with open(path, "wb") as f:
            writer.write(f)

    # 1. Combine Page 1 only
    combined_p1 = tmp_path / "combined_p1.pdf"
    count1 = combine_page1_only([pdf1_path, pdf2_path], combined_p1)
    assert count1 == 2
    reader1 = PdfReader(str(combined_p1))
    assert len(reader1.pages) == 2

    # 2. Combine all pages together
    combined_all = tmp_path / "combined_all.pdf"
    count_all = combine_all_pages_together([pdf1_path, pdf2_path], combined_all)
    assert count_all == 4
    reader_all = PdfReader(str(combined_all))
    assert len(reader_all.pages) == 4

    # 3. Combine separate pages
    sep_p1 = tmp_path / "sep_p1.pdf"
    sep_p2 = tmp_path / "sep_p2.pdf"
    p1_count, p2_count = combine_separate_pages([pdf1_path, pdf2_path], sep_p1, sep_p2)
    assert p1_count == 2
    assert p2_count == 2
    assert len(PdfReader(str(sep_p1)).pages) == 2
    assert len(PdfReader(str(sep_p2)).pages) == 2
