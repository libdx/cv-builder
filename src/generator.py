"""
PDF generation for the CV system.

Renders a self-contained HTML string to an A4 PDF using Playwright's
headless Chromium. Because the HTML embeds its own CSS and images (see
renderer.py), no web server or asset resolution is required — we load the
HTML directly via set_content.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright


class PDFGenerator:
    """Converts self-contained HTML into a print-quality A4 PDF."""

    def __init__(self, vertical: str = "13mm", horizontal: str = "14mm"):
        """
        Args:
            vertical: top/bottom physical page margin, applied to EVERY sheet
                by the print engine (so page 2+ get a proper top margin —
                container padding alone cannot do this).
            horizontal: left/right physical page margin.

        The print-only CSS override in layout.css drops .cv-page padding so
        these page margins are the single source of page spacing in PDFs.
        """
        self.vertical = vertical
        self.horizontal = horizontal

    def generate(self, html: str, output_path: Path) -> Path:
        """
        Render HTML to a PDF file.

        Args:
            html: Self-contained HTML document (CSS + images inlined).
            output_path: Destination .pdf path.

        Returns:
            The output path written.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                # Load inline so relative asset resolution is never needed.
                page.set_content(html, wait_until="networkidle")
                page.pdf(
                    path=str(output_path),
                    format="A4",
                    print_background=True,
                    margin={
                        "top": self.vertical,
                        "right": self.horizontal,
                        "bottom": self.vertical,
                        "left": self.horizontal,
                    },
                )
            finally:
                browser.close()

        return output_path
