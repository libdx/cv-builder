"""
PDF regression guards (require Playwright Chromium; auto-skip if absent).

These lock in the properties we previously had to verify by hand:
- page counts per variant (freelance must stay one page)
- complete repeated headers, including on a synthetic document beyond page 2
- header/body separation and an embedded photo on every sheet
- deterministic sidebar section distribution without duplication
- every sheet has real margins — guards the `@page { margin: 0 }` class of
  bug where margins (incl. page-2 top) silently zeroed out
- text is selectable (not rasterized)

Page counts track the CURRENT cv_data.yaml. If the CV content changes
materially, update EXPECTED_PAGES intentionally.
"""

import re

import fitz  # pymupdf
import pytest

PT_PER_MM = 72 / 25.4

# Expected pages for the current data set.
EXPECTED_PAGES = {
    "employment": 2,
    "contracting": 2,
    "freelance": 1,
    "freelance-extended": 2,
}

# Margin tolerance (mm). Floor well above 0 to catch zeroed margins;
# ceiling loose enough to tolerate font/engine variance.
MIN_SIDE = 10.0
MAX_SIDE = 18.0
MIN_HEADER_BODY_GAP = 2.0
MIN_HEADER_PHOTO_SIZE = 20.0
MIN_HEADER_RULE_WIDTH = 150.0
SIDEBAR_SECTIONS = (
    "Contact",
    "Skills",
    "Education",
    "Languages",
)
FIRST_PAGE_SIDEBAR_SECTIONS = SIDEBAR_SECTIONS[:3]
CONTINUATION_SIDEBAR_SECTIONS = SIDEBAR_SECTIONS[3:]


def _normalized_text(value):
    """Remove spacing/punctuation so letter-spaced PDF text is comparable."""
    return re.sub(r"[^\w]", "", value, flags=re.UNICODE).casefold()


def _header_rule(page):
    """Return the wide horizontal rule below the repeated header."""
    candidates = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if (
            rect.width / PT_PER_MM >= MIN_HEADER_RULE_WIDTH
            and rect.height / PT_PER_MM <= 1.0
        ):
            candidates.append(rect)
    assert len(candidates) == 1, f"expected one header rule, got {len(candidates)}"
    return candidates[0]


def _text_spans(page):
    """Yield text span rectangles from a PDF page."""
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                yield fitz.Rect(span["bbox"])


def _page_margins_mm(page):
    """Return (top, bottom, left, right) whitespace margins in mm."""
    pr = page.rect
    bbox = fitz.Rect(pr.x1, pr.y1, pr.x0, pr.y0)  # inverted seed
    for b in page.get_text("dict")["blocks"]:
        bbox |= fitz.Rect(b["bbox"])
    for d in page.get_drawings():
        bbox |= d["rect"]
    return (
        (bbox.y0 - pr.y0) / PT_PER_MM,
        (pr.y1 - bbox.y1) / PT_PER_MM,
        (bbox.x0 - pr.x0) / PT_PER_MM,
        (pr.x1 - bbox.x1) / PT_PER_MM,
    )


def _sidebar_text(page):
    """Extract normalized body spans from the left half of a PDF page."""
    rule = _header_rule(page)
    clip = fitz.Rect(page.rect.x0, rule.y1, page.rect.width / 2, page.rect.y1)
    return [
        _normalized_text(span["text"])
        for block in page.get_text("dict", clip=clip)["blocks"]
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    ]


def _assert_sidebar_sections(page, *, present, absent, context):
    text = _sidebar_text(page)
    for heading in present:
        assert _normalized_text(heading) in text, f"{context}: {heading} missing"
    for heading in absent:
        assert _normalized_text(heading) not in text, f"{context}: {heading} duplicated"


def _assert_text_order(text, expected, context):
    """Assert semantic reading order after normalizing PDF extraction noise."""
    normalized = _normalized_text(text)
    cursor = -1
    for value in expected:
        needle = _normalized_text(value)
        index = normalized.find(needle, cursor + 1)
        assert index >= 0, f"{context}: '{value}' missing or out of order"
        cursor = index


def _assert_vertical_proximity(page, before, after, *, max_gap_mm, context):
    """Assert related engagement text remains visually adjacent and ordered."""
    before_rects = page.search_for(before)
    after_rects = page.search_for(after)
    assert before_rects and after_rects, f"{context}: proximity anchors missing"
    gap_mm = (after_rects[0].y0 - before_rects[-1].y1) / PT_PER_MM
    assert -1.0 <= gap_mm <= max_gap_mm, f"{context}: gap={gap_mm:.1f}mm"


class TestPageCount:
    def test_expected_page_counts(self, built_pdfs):
        for variant, expected in EXPECTED_PAGES.items():
            with fitz.open(built_pdfs[variant]) as doc:
                assert (
                    doc.page_count == expected
                ), f"{variant}: expected {expected} page(s), got {doc.page_count}"

    def test_long_document_exercises_more_than_two_pages(self, built_pdfs):
        with fitz.open(built_pdfs["employment-long"]) as doc:
            assert doc.page_count >= 3


class TestRepeatedHeader:
    def test_identity_text_appears_on_every_page(self, built_pdfs, real_cv_data):
        expected_name = _normalized_text(
            f"{real_cv_data.personal_info.first_name} "
            f"{real_cv_data.personal_info.last_name}"
        )
        expected_title = _normalized_text(real_cv_data.personal_info.title)

        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                for i, page in enumerate(doc, 1):
                    text = _normalized_text(page.get_text())
                    assert expected_name in text, f"{variant} p{i}: name missing"
                    assert expected_title in text, f"{variant} p{i}: title missing"

    def test_photo_appears_above_rule_on_every_page(self, built_pdfs):
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                for i, page in enumerate(doc, 1):
                    rule = _header_rule(page)
                    photo_rects = [
                        rect
                        for image in page.get_images(full=True)
                        for rect in page.get_image_rects(image[0])
                        if rect.width / PT_PER_MM >= MIN_HEADER_PHOTO_SIZE
                        and rect.height / PT_PER_MM >= MIN_HEADER_PHOTO_SIZE
                        and rect.y0 < rule.y0
                    ]
                    assert photo_rects, f"{variant} p{i}: photo missing"
                    assert (
                        max(rect.y1 for rect in photo_rects) <= rule.y0
                    ), f"{variant} p{i}: photo overlaps header rule"

    def test_rule_separates_header_and_body_on_every_page(self, built_pdfs):
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                for i, page in enumerate(doc, 1):
                    rule = _header_rule(page)
                    body_tops = [
                        rect.y0 for rect in _text_spans(page) if rect.y0 > rule.y1
                    ]
                    assert body_tops, f"{variant} p{i}: body text missing"
                    gap = (min(body_tops) - rule.y1) / PT_PER_MM
                    assert (
                        gap >= MIN_HEADER_BODY_GAP
                    ), f"{variant} p{i}: header/body gap={gap:.1f}mm"


class TestSidebarPagination:
    @pytest.mark.parametrize("variant", ["employment", "contracting"])
    def test_multi_page_variants_use_deterministic_split(self, built_pdfs, variant):
        with fitz.open(built_pdfs[variant]) as doc:
            assert doc.page_count == 2
            _assert_sidebar_sections(
                doc[0],
                present=FIRST_PAGE_SIDEBAR_SECTIONS,
                absent=CONTINUATION_SIDEBAR_SECTIONS,
                context=f"{variant} p1",
            )
            _assert_sidebar_sections(
                doc[1],
                present=CONTINUATION_SIDEBAR_SECTIONS,
                absent=FIRST_PAGE_SIDEBAR_SECTIONS,
                context=f"{variant} p2",
            )

            sidebar_text = [span for page in doc for span in _sidebar_text(page)]
            for heading in SIDEBAR_SECTIONS:
                assert (
                    sidebar_text.count(_normalized_text(heading)) == 1
                ), f"{variant}: {heading} must appear exactly once"

    def test_freelance_keeps_all_sections_on_its_single_page(self, built_pdfs):
        with fitz.open(built_pdfs["freelance"]) as doc:
            assert doc.page_count == 1
            _assert_sidebar_sections(
                doc[0],
                present=SIDEBAR_SECTIONS,
                absent=(),
                context="freelance p1",
            )

    def test_freelance_extended_moves_languages_to_page_two(self, built_pdfs):
        with fitz.open(built_pdfs["freelance-extended"]) as doc:
            assert doc.page_count == 2
            _assert_sidebar_sections(
                doc[0],
                present=FIRST_PAGE_SIDEBAR_SECTIONS,
                absent=CONTINUATION_SIDEBAR_SECTIONS,
                context="freelance-extended p1",
            )
            _assert_sidebar_sections(
                doc[1],
                present=CONTINUATION_SIDEBAR_SECTIONS,
                absent=FIRST_PAGE_SIDEBAR_SECTIONS,
                context="freelance-extended p2",
            )

    def test_long_document_places_continuation_on_page_two_only(self, built_pdfs):
        with fitz.open(built_pdfs["employment-long"]) as doc:
            assert doc.page_count >= 3
            _assert_sidebar_sections(
                doc[0],
                present=FIRST_PAGE_SIDEBAR_SECTIONS,
                absent=CONTINUATION_SIDEBAR_SECTIONS,
                context="employment-long p1",
            )
            _assert_sidebar_sections(
                doc[1],
                present=CONTINUATION_SIDEBAR_SECTIONS,
                absent=FIRST_PAGE_SIDEBAR_SECTIONS,
                context="employment-long p2",
            )
            for page_number, page in enumerate(doc[2:], 3):
                _assert_sidebar_sections(
                    page,
                    present=(),
                    absent=SIDEBAR_SECTIONS,
                    context=f"employment-long p{page_number}",
                )


class TestMargins:
    def test_every_page_has_margins(self, built_pdfs):
        """Guards the margin-zeroing regression on ALL pages (incl. page 2)."""
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                for i, page in enumerate(doc, 1):
                    top, bottom, left, right = _page_margins_mm(page)
                    assert (
                        MIN_SIDE <= top <= MAX_SIDE
                    ), f"{variant} p{i} top={top:.1f}mm"
                    assert (
                        MIN_SIDE <= left <= MAX_SIDE
                    ), f"{variant} p{i} left={left:.1f}mm"
                    assert (
                        MIN_SIDE <= right <= MAX_SIDE
                    ), f"{variant} p{i} right={right:.1f}mm"
                    # content must not bleed into the bottom margin (no upper
                    # bound: a short final page legitimately has large bottom)
                    assert bottom >= MIN_SIDE, f"{variant} p{i} bottom={bottom:.1f}mm"


class TestSelectableText:
    def test_text_is_extractable_on_every_page(self, built_pdfs):
        """Output is real text, not a rasterized image."""
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                for i, page in enumerate(doc, 1):
                    assert (
                        page.get_text().strip()
                    ), f"{variant} p{i}: no selectable text"


class TestDefaultContentPolicy:
    def test_interests_are_absent_from_all_outputs(self, built_pdfs):
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                text = _normalized_text(" ".join(page.get_text() for page in doc))
                assert (
                    _normalized_text("Interests") not in text
                ), f"{variant}: Interests must be omitted"

    def test_non_verified_career_evidence_is_absent(self, built_pdfs):
        non_verified_claims = (
            "Reduced deployment lead time by an unconfirmed amount.",
            "Example company has an unverified funding stage.",
            "Improved customer adoption by an unconfirmed amount.",
            "Example analytics product has an unverified funding stage.",
            "Reduced import duration by an unconfirmed amount.",
        )
        for variant, path in built_pdfs.items():
            with fitz.open(path) as doc:
                text = _normalized_text(" ".join(page.get_text() for page in doc))
                for claim in non_verified_claims:
                    assert (
                        _normalized_text(claim) not in text
                    ), f"{variant}: non-verified career evidence rendered"


class TestFreelanceEditionContent:
    def test_earlier_history_is_not_split_from_its_dates(self, built_pdfs):
        with fitz.open(built_pdfs["freelance-extended"]) as doc:
            pages = [page.get_text() for page in doc]
        learning_page = next(text for text in pages if "EXAMPLE LEARNING" in text)
        assert "2014" in learning_page and "2016" in learning_page
        assert "Software Engineer → Senior Software Engineer" in learning_page

    def test_concise_is_one_page_consultancy_with_engagements(self, built_pdfs):
        with fitz.open(built_pdfs["freelance"]) as doc:
            text = " ".join(page.get_text() for page in doc)
            assert "INDEPENDENT CONSULTING" in text
            assert "SELECTED CLIENT ENGAGEMENTS" in text
            assert "Commerce SaaS platform" in text
            assert "Reporting and analytics platform" in text
            assert "Example Consulting" in text
            assert "Example Workflow" not in text
            assert "Confidential" not in text

    def test_extended_adds_verified_depth_and_earlier_history(self, built_pdfs):
        with fitz.open(built_pdfs["freelance-extended"]) as doc:
            text = " ".join(page.get_text() for page in doc)
            assert (
                "Document service boundaries and compare technical options with the team."
                in text
            )
            assert "Example Workflow" in text
            assert "EARLIER SOFTWARE ENGINEERING" in text
            assert (
                _normalized_text(text).count(_normalized_text("Example Learning")) == 1
            )
            assert "Confidential" not in text

    @pytest.mark.parametrize("output", ["freelance", "freelance-extended"])
    def test_engagements_extract_as_coherent_case_studies(self, built_pdfs, output):
        with fitz.open(built_pdfs[output]) as doc:
            text = " ".join(page.get_text(sort=False) for page in doc)

        _assert_text_order(
            text,
            (
                "Commerce SaaS platform",
                "Develop Python services",
                "Contributions",
                "Implement Django services with background jobs and database migrations.",
                "Build versioned REST APIs for catalogue and checkout workflows.",
                "Technologies Python, Django",
                "Reporting and analytics platform",
                "Deliver reporting features",
                "Contributions",
                "Build connectors that import structured reports from external APIs.",
                "Maintain container builds and automated deployment checks.",
                "Technologies Python, AWS",
                "Outcomes",
                "Established a repeatable onboarding checklist for new team members.",
            ),
            output,
        )

    @pytest.mark.parametrize("output", ["freelance", "freelance-extended"])
    def test_engagement_context_and_scope_are_visually_adjacent(
        self, built_pdfs, output
    ):
        with fitz.open(built_pdfs[output]) as doc:
            page = doc[0]
            _assert_vertical_proximity(
                page,
                "Commerce SaaS platform",
                "Develop Python services",
                max_gap_mm=5.0,
                context=f"{output}: commerce engagement",
            )
            _assert_vertical_proximity(
                page,
                "Reporting and analytics platform",
                "Deliver reporting features",
                max_gap_mm=5.0,
                context=f"{output}: analytics engagement",
            )
