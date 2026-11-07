"""Structural regression coverage for editable DOCX output."""

import re
from pathlib import Path
from zipfile import ZipFile

import pytest

docx = pytest.importorskip("docx")

from docx_generator import DocxGenerator
from transforms import CVTransformer

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def built_docx(real_cv_data, tmp_path_factory):
    data = CVTransformer(real_cv_data).transform("freelance", edition="extended")
    path = tmp_path_factory.mktemp("docx") / "freelance-extended.docx"
    DocxGenerator(project_root=PROJECT_ROOT).generate(data, path)
    return path, data


def test_docx_is_a4_with_repeating_header(built_docx):
    path, data = built_docx
    document = docx.Document(path)
    section = document.sections[0]

    assert section.page_width.mm == pytest.approx(210, abs=0.1)
    assert section.page_height.mm == pytest.approx(297, abs=0.1)
    assert document.settings.odd_and_even_pages_header_footer is False
    assert section.different_first_page_header_footer is False

    personal = data["personal_info"]
    header = section.header
    assert header.is_linked_to_previous is False
    header_text = " ".join(
        cell.text for table in header.tables for row in table.rows for cell in row.cells
    )
    assert personal["first_name"].upper() in header_text
    assert personal["last_name"].upper() in header_text
    assert personal["title"] in header_text

    header_table = header.tables[0]
    assert name_not_in_cell(personal, header_table.cell(0, 0).text)
    assert personal["first_name"].upper() in header_table.cell(0, 1).text
    assert personal["last_name"].upper() in header_table.cell(0, 1).text


def test_docx_contains_editable_cv_text_and_no_text_boxes(built_docx):
    path, data = built_docx
    document = docx.Document(path)
    visible_text = " ".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )
    visible_text = re.sub(r"\s+", " ", visible_text)

    with ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode()

    assert re.sub(r"\s+", " ", data["profile"].strip()) in visible_text
    assert data["consultancy"]["title"] in visible_text
    assert data["engagements"][0]["context"] in visible_text
    assert "w:txbxContent" not in document_xml


def test_docx_uses_native_hyperlinks_and_embedded_photo(built_docx):
    path, _ = built_docx
    with ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode()
        relationships = archive.read("word/_rels/document.xml.rels").decode()
        header_relationships = " ".join(
            archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith("word/_rels/header") and name.endswith(".xml.rels")
        )
        header_xml = " ".join(
            archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith("word/header") and name.endswith(".xml")
        )

    assert "w:hyperlink" in document_xml
    assert 'TargetMode="External"' in relationships
    assert "relationships/image" in header_relationships
    assert 'prst="ellipse"' in header_xml


def test_docx_has_native_two_column_body_table(built_docx):
    path, _ = built_docx
    document = docx.Document(path)

    assert len(document.tables) == 2
    body_table = document.tables[0]
    assert len(body_table.columns) == 2
    assert "CONTACT" in body_table.cell(0, 0).text
    assert "PROFILE" in body_table.cell(0, 1).text

    continuation_table = document.tables[1]
    assert len(continuation_table.columns) == 2
    assert "LANGUAGES" in continuation_table.cell(0, 0).text
    assert "CONTACT" not in continuation_table.cell(0, 0).text
    assert "SELECTED PRIOR EMPLOYMENT" not in body_table.cell(0, 1).text
    assert "SELECTED PRIOR EMPLOYMENT" in continuation_table.cell(0, 1).text

    with ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode()
    assert 'w:type="page"' in document_xml


def test_engagement_outcomes_precede_technology_summary(built_docx):
    path, data = built_docx
    document = docx.Document(path)
    visible_text = " ".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )
    engagement = next(item for item in data["engagements"] if item.get("outcomes"))
    engagement_start = visible_text.index(engagement["context"])
    assert visible_text.index(
        engagement["outcomes"][-1], engagement_start
    ) < visible_text.index(", ".join(engagement["technologies"]), engagement_start)


def name_not_in_cell(personal, text):
    return (
        personal["first_name"].upper() not in text
        and personal["last_name"].upper() not in text
    )
