"""Editable Word export for transformed CV data.

The DOCX renderer consumes the same transformed dictionary as the HTML
renderer. It does not parse HTML or attempt to translate CSS. The document
uses native Word paragraphs, hyperlinks, tables, headers, and images so its
text remains editable and extractable.
"""

from pathlib import Path
from math import ceil
from typing import Any, Dict, Iterable, Optional

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor


FONT_NAME = "Arial"
TEXT = "2B2B2B"
MUTED = "6F6F6F"
RULE = "D9D9D9"


class DocxGenerator:
    """Render one transformed CV into an editable A4 DOCX."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent

    def generate(self, data: Dict[str, Any], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = Document()
        self._configure_document(document, data)
        self._add_header(document, data)
        self._add_body(document, data)
        document.save(output_path)
        return output_path

    def _configure_document(self, document, data: Dict[str, Any]) -> None:
        section = document.sections[0]
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Mm(14)
        section.right_margin = Mm(14)
        section.top_margin = Mm(39)
        section.bottom_margin = Mm(13)
        section.header_distance = Mm(9)

        normal = document.styles["Normal"]
        normal.font.name = FONT_NAME
        normal.font.size = Pt(9.4)
        normal.font.color.rgb = RGBColor.from_string(TEXT)
        self._set_style_font(normal, FONT_NAME)
        normal.paragraph_format.space_after = Pt(3)
        normal.paragraph_format.line_spacing = 1.08

        personal = data["personal_info"]
        name = f"{personal['first_name']} {personal['last_name']}"
        document.core_properties.title = f"{name} CV"
        document.core_properties.subject = personal["title"]
        document.core_properties.author = name
        document.core_properties.last_modified_by = "CV Builder"
        document.core_properties.comments = ""

    def _add_header(self, document, data: Dict[str, Any]) -> None:
        section = document.sections[0]
        header = section.header
        header.is_linked_to_previous = False
        self._populate_header(header, data)

    def _populate_header(self, header, data: Dict[str, Any]) -> None:
        table = header.add_table(rows=1, cols=2, width=Mm(182))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        table.columns[0].width = Mm(32)
        table.columns[1].width = Mm(150)
        self._set_table_layout_fixed(table)
        self._set_table_borders(table, bottom=(RULE, 8))

        photo_cell = table.cell(0, 0)
        identity = table.cell(0, 1)
        identity.width = Mm(150)
        photo_cell.width = Mm(32)
        photo_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        self._set_cell_margins(photo_cell, top=0, right=5, bottom=2, left=0)
        self._set_cell_margins(identity, top=0, right=0, bottom=2, left=1)

        personal = data["personal_info"]
        name = f"{personal['first_name']} {personal['last_name']}"
        paragraph = identity.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(1)
        run = paragraph.add_run(name.upper())
        self._format_run(run, size=22, bold=True, color="1F1F1F")

        paragraph = identity.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(personal["title"])
        self._format_run(run, size=9.5, color=MUTED)

        photo_path = personal.get("photo")
        if photo_path:
            resolved = (self.project_root / photo_path).resolve()
            if resolved.is_file():
                paragraph = photo_cell.paragraphs[0]
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.space_after = Pt(0)
                run = paragraph.add_run()
                run.add_picture(str(resolved), width=Mm(25))
                self._set_picture_alt_text(run, f"Portrait of {name}")
                self._set_picture_shape(run, "ellipse")

    def _add_body(self, document, data: Dict[str, Any]) -> None:
        # Stage each region independently, then place page-sized groups in
        # separate tables with normal page breaks between them. LibreOffice can
        # paint a multi-page table row over the header on pages where the row
        # starts; explicit page tables avoid that renderer-specific defect.
        staging = document.add_table(rows=1, cols=3)
        self._fill_sidebar(staging.cell(0, 0), data, "sidebar_primary")
        self._fill_sidebar(staging.cell(0, 1), data, "sidebar_continuation")
        self._fill_main(staging.cell(0, 2), data)
        primary_blocks = [paragraph._p for paragraph in staging.cell(0, 0).paragraphs]
        continuation_blocks = [
            paragraph._p for paragraph in staging.cell(0, 1).paragraphs
        ]
        main_paragraphs = list(staging.cell(0, 2).paragraphs)
        main_pages = (
            [main_paragraphs]
            if len(main_paragraphs) <= 23
            else self._chunk_paragraphs(main_paragraphs)
        )

        for page_index, main_page in enumerate(main_pages):
            if page_index:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.add_run().add_break(WD_BREAK.PAGE)
            # Keep the body table from being the first layout object on a
            # page. LibreOffice otherwise lets the table paint through the
            # header area on alternating pages.
            anchor = document.add_paragraph()
            anchor.paragraph_format.space_after = Pt(0)
            anchor.paragraph_format.line_spacing = Pt(1)
            sidebar_blocks = (
                primary_blocks
                if page_index == 0
                else continuation_blocks if page_index == 1 else []
            )
            self._add_body_page(
                document,
                sidebar_blocks,
                [paragraph._p for paragraph in main_page],
            )

        staging._element.getparent().remove(staging._element)

    def _add_body_page(self, document, sidebar_blocks, main_blocks) -> None:
        table = document.add_table(rows=1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        table.columns[0].width = Mm(58)
        table.columns[1].width = Mm(124)
        self._set_table_layout_fixed(table)
        self._set_table_borders(table)

        row = table.rows[0]
        self._prevent_row_split(row)
        sidebar, main = row.cells
        sidebar.width = Mm(58)
        main.width = Mm(124)
        sidebar.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        main.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        self._set_cell_margins(sidebar, top=0, right=6, bottom=0, left=0)
        self._set_cell_margins(main, top=0, right=0, bottom=0, left=7)
        self._set_cell_border(sidebar, "right", RULE, 8)
        self._replace_cell_content(sidebar, sidebar_blocks)
        self._replace_cell_content(main, main_blocks)

    def _fill_sidebar(self, cell, data: Dict[str, Any], placement: str) -> None:
        self._clear_cell(cell)
        for section in data["sidebar"]:
            if section["placement"] != placement:
                continue
            section_id = section["id"]
            if section_id == "contact":
                self._sidebar_contact(cell, data["contact"])
            elif section_id == "skills":
                self._sidebar_skills(cell, data["skills"])
            elif section_id == "education":
                self._sidebar_education(cell, data["education"])
            elif section_id == "languages":
                self._sidebar_languages(cell, data["languages"])
            elif section_id == "interests":
                self._sidebar_interests(cell, data["interests"])

    def _sidebar_contact(self, cell, contact: Dict[str, str]) -> None:
        self._section_heading(cell, "Contact", sidebar=True)
        values = [
            (contact["phone"], f"tel:{contact['phone'].replace(' ', '')}"),
            (contact["email"], f"mailto:{contact['email']}"),
            (contact["location"], None),
            (contact["linkedin"], self._external_url(contact["linkedin"])),
        ]
        for label, url in values:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(3)
            if url:
                self._add_hyperlink(paragraph, label, url)
            else:
                run = paragraph.add_run(label)
                self._format_run(run, size=8.5)

    def _sidebar_skills(self, cell, skills: Dict[str, Any]) -> None:
        self._section_heading(cell, "Skills", sidebar=True)
        for group in skills["technical"]:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(3)
            label = paragraph.add_run(f"{group['label']}: ")
            self._format_run(label, size=8.4, bold=True)
            values = paragraph.add_run(", ".join(group["items"]))
            self._format_run(values, size=8.4)
        if skills["capabilities"]:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(3)
            paragraph.paragraph_format.space_after = Pt(2)
            run = paragraph.add_run("Capabilities")
            self._format_run(run, size=8.5, bold=True)
            for capability in skills["capabilities"]:
                paragraph = cell.add_paragraph(style=None)
                paragraph.paragraph_format.left_indent = Mm(3)
                paragraph.paragraph_format.first_line_indent = Mm(-3)
                paragraph.paragraph_format.space_after = Pt(1.5)
                run = paragraph.add_run(f"• {capability}")
                self._format_run(run, size=8.3)

    def _sidebar_education(self, cell, education: Iterable[Dict[str, Any]]) -> None:
        self._section_heading(cell, "Education", sidebar=True)
        for entry in education:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run(entry["degree"])
            self._format_run(run, size=8.5, bold=True)
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run(entry["institution"])
            self._format_run(run, size=8.3)
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(3)
            run = paragraph.add_run(f"{entry['start_year']} – {entry['end_year']}")
            self._format_run(run, size=8, color=MUTED)

    def _sidebar_languages(self, cell, languages: Iterable[Dict[str, str]]) -> None:
        self._section_heading(cell, "Languages", sidebar=True)
        for language in languages:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(1)
            run = paragraph.add_run(language["name"])
            self._format_run(run, size=8.5, bold=True)
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(3)
            run = paragraph.add_run(language["proficiency"])
            self._format_run(run, size=8, color=MUTED)

    def _sidebar_interests(self, cell, interests: Iterable[str]) -> None:
        values = list(interests)
        if not values:
            return
        self._section_heading(cell, "Interests", sidebar=True)
        paragraph = cell.add_paragraph()
        run = paragraph.add_run(", ".join(values))
        self._format_run(run, size=8.3)

    def _fill_main(self, cell, data: Dict[str, Any]) -> None:
        self._clear_cell(cell)
        self._section_heading(cell, "Profile")
        self._body_paragraph(cell, data["profile"].strip(), space_after=7)

        practice = data.get("practice_evidence") or []
        if practice:
            self._section_heading(cell, "AI Native Engineering")
            for item in practice:
                self._bullet(cell, item["statement"])

        if data["variant"] == "freelance":
            self._freelance_content(cell, data)
        else:
            self._section_heading(cell, "Work Experience")
            for job in data.get("experience", []):
                self._job(cell, job)

    def _freelance_content(self, cell, data: Dict[str, Any]) -> None:
        self._section_heading(cell, "Independent Consulting")
        consultancy = data["consultancy"]
        self._title_meta(
            cell,
            consultancy["title"],
            self._date_range(consultancy["start_date"], consultancy["end_date"]),
        )
        engagements = data.get("engagements", [])
        if engagements:
            self._subheading(cell, "Selected Client Engagements")
            for engagement in engagements:
                self._engagement(cell, engagement)

        for heading, key in (
            ("Selected Experience", "selected_experience"),
            ("Selected Prior Employment", "prior_employment"),
        ):
            jobs = data.get(key, [])
            if jobs:
                self._section_heading(cell, heading)
                for job in jobs:
                    self._job(cell, job)

        earlier = data.get("earlier_history", [])
        if earlier:
            self._section_heading(cell, "Earlier Software Engineering")
            for entry in earlier:
                title = entry["company"]
                meta = (
                    f"{self._date_range(entry['start_date'], entry['end_date'])}"
                    f" | {' → '.join(entry['titles'])}"
                )
                self._title_meta(cell, title, meta, compact=True)

    def _engagement(self, cell, engagement: Dict[str, Any]) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(engagement["context"])
        self._format_run(run, size=9.8, bold=True)
        for statement in engagement.get("scope", []):
            self._body_paragraph(cell, statement, space_after=2)
        for statement in engagement.get("contributions", []):
            self._bullet(cell, statement)
        for statement in engagement.get("outcomes", []):
            self._bullet(cell, statement)
        self._technology_line(cell, engagement.get("technologies", []))

    def _job(self, cell, job: Dict[str, Any]) -> None:
        company_meta = job["company"]
        if job.get("start_date"):
            company_meta += f" | {self._date_range(job['start_date'], job['end_date'])}"
        self._title_meta(cell, job["title"], company_meta)
        self._technology_line(cell, job.get("technologies", []))
        if job.get("description"):
            self._body_paragraph(cell, job["description"], space_after=2)
        for statement in job.get("achievements", []):
            self._bullet(cell, statement)

    def _section_heading(self, cell, text: str, sidebar: bool = False) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(8 if not sidebar else 6)
        paragraph.paragraph_format.space_after = Pt(5 if not sidebar else 4)
        run = paragraph.add_run(text.upper())
        self._format_run(run, size=10.5 if not sidebar else 9.5, bold=True)

    def _subheading(self, cell, text: str) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(6)
        paragraph.paragraph_format.space_after = Pt(4)
        run = paragraph.add_run(text)
        self._format_run(run, size=9.5, bold=True)

    def _title_meta(
        self, cell, title: str, meta: str, *, compact: bool = False
    ) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.space_before = Pt(4 if compact else 6)
        paragraph.paragraph_format.space_after = Pt(1)
        run = paragraph.add_run(title)
        self._format_run(run, size=9.8 if compact else 10.1, bold=True)
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.keep_with_next = not compact
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(meta)
        self._format_run(run, size=8.3, color=MUTED)

    def _body_paragraph(self, cell, text: str, *, space_after: float = 3) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(space_after)
        run = paragraph.add_run(text)
        self._format_run(run, size=9.2)

    def _bullet(self, cell, text: str) -> None:
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.left_indent = Mm(3.5)
        paragraph.paragraph_format.first_line_indent = Mm(-3.5)
        paragraph.paragraph_format.space_after = Pt(2)
        run = paragraph.add_run(f"• {text}")
        self._format_run(run, size=9)

    def _technology_line(self, cell, technologies: Iterable[str]) -> None:
        values = list(technologies)
        if not values:
            return
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        label = paragraph.add_run("Technologies: ")
        self._format_run(label, size=8.1, bold=True, color=MUTED)
        value = paragraph.add_run(", ".join(values))
        self._format_run(value, size=8.1, color=MUTED)

    @staticmethod
    def _date_range(start_date: str, end_date: str) -> str:
        return f"{start_date.split('-')[0]} – {end_date.split('-')[0]}"

    @staticmethod
    def _external_url(value: str) -> str:
        return (
            value if value.startswith(("http://", "https://")) else f"https://{value}"
        )

    def _add_hyperlink(self, paragraph, text: str, url: str) -> None:
        relationship_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship_id)
        run = OxmlElement("w:r")
        properties = OxmlElement("w:rPr")
        color = OxmlElement("w:color")
        color.set(qn("w:val"), TEXT)
        properties.append(color)
        fonts = OxmlElement("w:rFonts")
        fonts.set(qn("w:ascii"), FONT_NAME)
        fonts.set(qn("w:hAnsi"), FONT_NAME)
        properties.append(fonts)
        size = OxmlElement("w:sz")
        size.set(qn("w:val"), "17")
        properties.append(size)
        run.append(properties)
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
        hyperlink.append(run)
        paragraph._p.append(hyperlink)

    def _format_run(
        self,
        run,
        *,
        size: float,
        bold: bool = False,
        color: str = TEXT,
    ) -> None:
        run.font.name = FONT_NAME
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor.from_string(color)
        properties = run._element.get_or_add_rPr()
        fonts = properties.get_or_add_rFonts()
        fonts.set(qn("w:ascii"), FONT_NAME)
        fonts.set(qn("w:hAnsi"), FONT_NAME)

    @staticmethod
    def _set_style_font(style, font_name: str) -> None:
        properties = style.element.get_or_add_rPr()
        fonts = properties.get_or_add_rFonts()
        fonts.set(qn("w:ascii"), font_name)
        fonts.set(qn("w:hAnsi"), font_name)

    @staticmethod
    def _clear_cell(cell) -> None:
        for paragraph in list(cell.paragraphs):
            paragraph._element.getparent().remove(paragraph._element)

    @staticmethod
    def _replace_cell_content(cell, paragraph_elements) -> None:
        for child in list(cell._tc):
            if child.tag == qn("w:p"):
                cell._tc.remove(child)
        if not paragraph_elements:
            cell.add_paragraph()
        else:
            for paragraph_element in paragraph_elements:
                cell._tc.append(paragraph_element)

    @staticmethod
    def _chunk_paragraphs(paragraphs, max_height_points: float = 540):
        """Group paragraphs into page-safe native table rows.

        The estimate deliberately leaves headroom for font-metric differences
        between Word and LibreOffice. Rows stay dense inside each page while
        avoiding a single table row that must span page boundaries. Word's
        ``keep_with_next`` flag is treated as a transitive grouping signal so
        a role title cannot be separated from its employer and opening detail.
        """
        blocks = []
        block = []
        for paragraph in paragraphs:
            block.append(paragraph)
            if not paragraph.paragraph_format.keep_with_next:
                blocks.append(block)
                block = []
        if block:
            blocks.append(block)

        # In the extended freelance edition, prior employment is supporting
        # evidence rather than part of the consulting narrative. Prefer a
        # deliberate page boundary before it when both resulting pages remain
        # within the conservative page-height budget.
        for index, candidate in enumerate(blocks[1:], start=1):
            first_text = candidate[0].text.strip().upper()
            if first_text not in {"SELECTED PRIOR EMPLOYMENT", "SELECTED EXPERIENCE"}:
                continue
            first_height = sum(
                DocxGenerator._estimated_paragraph_height(paragraph)
                for block in blocks[:index]
                for paragraph in block
            )
            second_height = sum(
                DocxGenerator._estimated_paragraph_height(paragraph)
                for block in blocks[index:]
                for paragraph in block
            )
            if first_height <= max_height_points and second_height <= max_height_points:
                return [
                    [paragraph for block in blocks[:index] for paragraph in block],
                    [paragraph for block in blocks[index:] for paragraph in block],
                ]

        chunks = []
        current = []
        current_height = 0.0
        for block in blocks:
            block_height = sum(
                DocxGenerator._estimated_paragraph_height(paragraph)
                for paragraph in block
            )
            if current and current_height + block_height > max_height_points:
                chunks.append(current)
                current = []
                current_height = 0.0
            current.extend(block)
            current_height += block_height
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _estimated_paragraph_height(paragraph) -> float:
        text = paragraph.text or " "
        line_count = max(1, ceil(len(text) / 66))
        sizes = [
            run.font.size.pt for run in paragraph.runs if run.font.size is not None
        ]
        font_size = max(sizes, default=9)
        before = paragraph.paragraph_format.space_before
        after = paragraph.paragraph_format.space_after
        estimated_height = font_size * 1.18 * line_count
        estimated_height += before.pt if before is not None else 0
        estimated_height += after.pt if after is not None else 0
        return estimated_height

    @staticmethod
    def _prevent_row_split(row) -> None:
        properties = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        properties.append(cant_split)

    @staticmethod
    def _set_table_layout_fixed(table) -> None:
        properties = table._tbl.tblPr
        layout = properties.first_child_found_in("w:tblLayout")
        if layout is None:
            layout = OxmlElement("w:tblLayout")
            properties.append(layout)
        layout.set(qn("w:type"), "fixed")

    @staticmethod
    def _set_table_borders(table, bottom=None) -> None:
        properties = table._tbl.tblPr
        borders = properties.first_child_found_in("w:tblBorders")
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            properties.append(borders)
        for edge in ("top", "left", "insideH", "insideV", "right"):
            element = OxmlElement(f"w:{edge}")
            element.set(qn("w:val"), "nil")
            borders.append(element)
        bottom_element = OxmlElement("w:bottom")
        if bottom is None:
            bottom_element.set(qn("w:val"), "nil")
        else:
            color, size = bottom
            bottom_element.set(qn("w:val"), "single")
            bottom_element.set(qn("w:color"), color)
            bottom_element.set(qn("w:sz"), str(size))
        borders.append(bottom_element)

    @staticmethod
    def _set_cell_border(cell, edge: str, color: str, size: int) -> None:
        properties = cell._tc.get_or_add_tcPr()
        borders = properties.first_child_found_in("w:tcBorders")
        if borders is None:
            borders = OxmlElement("w:tcBorders")
            properties.append(borders)
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:color"), color)
        element.set(qn("w:sz"), str(size))
        borders.append(element)

    @staticmethod
    def _set_cell_margins(
        cell, *, top: int, right: int, bottom: int, left: int
    ) -> None:
        properties = cell._tc.get_or_add_tcPr()
        margins = properties.first_child_found_in("w:tcMar")
        if margins is None:
            margins = OxmlElement("w:tcMar")
            properties.append(margins)
        for edge, millimeters in (
            ("top", top),
            ("right", right),
            ("bottom", bottom),
            ("left", left),
        ):
            element = OxmlElement(f"w:{edge}")
            # OOXML table-cell margins use twentieths of a point (twips),
            # whereas python-docx Length values are expressed as EMUs.
            element.set(qn("w:w"), str(round(millimeters * 56.6929)))
            element.set(qn("w:type"), "dxa")
            margins.append(element)

    @staticmethod
    def _set_picture_alt_text(run, description: str) -> None:
        drawing = run._element.find(qn("w:drawing"))
        if drawing is None:
            return
        doc_properties = drawing.find(".//" + qn("wp:docPr"))
        if doc_properties is not None:
            doc_properties.set("descr", description)

    @staticmethod
    def _set_picture_shape(run, preset: str) -> None:
        """Clip an inline picture with a native DrawingML preset shape."""
        drawing = run._element.find(qn("w:drawing"))
        if drawing is None:
            return
        geometry = drawing.find(".//" + qn("a:prstGeom"))
        if geometry is not None:
            geometry.set("prst", preset)
