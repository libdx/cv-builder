"""Tests for the optional ATS-compatibility diagnostic."""

import sys
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from ats_check import (  # noqa: E402
    audit_pdf,
    pages_with_parallel_columns,
    spaced_uppercase_lines,
    token_recall,
    visible_html_text,
)


def _write_pdf(path: Path, page_texts: list[list[tuple[tuple[int, int], str]]]) -> None:
    document = fitz.open()
    for text_items in page_texts:
        page = document.new_page()
        for point, text in text_items:
            page.insert_text(point, text)
    document.save(path)
    document.close()


def test_visible_html_text_ignores_metadata_and_styles():
    html = """
    <html><head><title>Hidden title</title><style>.x { color: red; }</style></head>
    <body><h1>Visible heading</h1><p>Visible body</p></body></html>
    """

    assert visible_html_text(html) == "Visible heading Visible body"


def test_token_recall_preserves_counts_and_lists_missing_tokens():
    recall, missing = token_recall("Python Python Django AWS", "Python Django AWS")

    assert recall == 0.75
    assert missing == ["python"]


def test_spaced_uppercase_lines_flags_decorative_text_only():
    text = "PROFILE\nP R I N C I P A L ENGINEER\nNormal title"

    assert spaced_uppercase_lines(text) == ["P R I N C I P A L ENGINEER"]


def test_parallel_column_detection_uses_overlapping_text_blocks(tmp_path):
    pdf_path = tmp_path / "columns.pdf"
    _write_pdf(
        pdf_path,
        [
            [
                ((50, 200), "Left sidebar line"),
                ((350, 209), "Right experience line"),
            ]
        ],
    )

    with fitz.open(pdf_path) as document:
        assert pages_with_parallel_columns(document) == [1]


def test_audit_reports_empty_page_and_repeated_top_content(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _write_pdf(
        pdf_path,
        [
            [((50, 50), "REPEATED HEADER"), ((50, 200), "Page one body text")],
            [((50, 50), "REPEATED HEADER")],
        ],
    )

    result = audit_pdf(pdf_path)
    findings = {finding.code: finding for finding in result.findings}

    assert result.pages == 2
    assert findings["selectable-text"].severity == "error"
    assert findings["repeated-top-content"].severity == "warning"


def test_audit_compares_pdf_with_matching_html(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    html_path = tmp_path / "sample.html"
    _write_pdf(pdf_path, [[((50, 100), "Python Django")]])
    html_path.write_text("<body>Python Django Kubernetes</body>", encoding="utf-8")

    result = audit_pdf(pdf_path, html_path=html_path)
    finding = next(
        finding for finding in result.findings if finding.code == "html-token-recall"
    )

    assert result.html_token_recall == 2 / 3
    assert finding.severity == "error"
    assert "kubernetes" in finding.evidence
