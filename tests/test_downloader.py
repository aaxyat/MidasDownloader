"""Tests for MidasDownloader parser, suggestions, and target generation."""

from pathlib import Path
from midasdownloader.downloader import (
    StudentTarget,
    deduplicate_targets,
    extract_id_from_entrance_no,
    parse_targets_from_file,
    parse_targets_from_range,
    parse_targets_from_text,
    suggest_url_template,
)


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


def test_report_xls_parsing():
    sample_file = Path("report_sample.xls")
    if sample_file.exists():
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
