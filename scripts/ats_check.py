#!/usr/bin/env python3
"""Deterministic, local ATS-compatibility diagnostics for generated CV PDFs.

This is deliberately not an "ATS score". It verifies observable PDF properties
and flags formatting patterns that documented ATS guidance identifies as risky.
When the matching generated HTML is available, it also measures how much visible
HTML text survives PDF extraction.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Sequence

import fitz

Severity = Literal["error", "warning"]

DEFAULT_MAX_SIZE_MB = 2.5
WARNING_TOKEN_RECALL = 0.995
ERROR_TOKEN_RECALL = 0.95


@dataclass(frozen=True)
class Finding:
    """One observable compatibility finding."""

    severity: Severity
    code: str
    message: str
    evidence: str | None = None


@dataclass(frozen=True)
class AuditResult:
    """Serializable result for one PDF."""

    path: str
    pages: int
    size_bytes: int
    extracted_characters: int
    html_token_recall: float | None
    findings: tuple[Finding, ...]

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)


class VisibleHTMLTextParser(HTMLParser):
    """Collect visible text while ignoring document metadata and code."""

    IGNORED_ELEMENTS = {"head", "script", "style", "template"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.IGNORED_ELEMENTS:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.IGNORED_ELEMENTS:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def visible_html_text(html: str) -> str:
    """Return whitespace-normalized visible text from generated HTML."""
    parser = VisibleHTMLTextParser()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


def tokens(text: str) -> list[str]:
    """Tokenize Unicode words consistently for extraction recall."""
    return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)


def token_recall(expected: str, extracted: str) -> tuple[float, list[str]]:
    """Return multiset recall and missing expected token occurrences."""
    expected_counts = Counter(tokens(expected))
    extracted_counts = Counter(tokens(extracted))
    expected_total = sum(expected_counts.values())
    if expected_total == 0:
        return 1.0, []

    matched = sum(
        min(count, extracted_counts[token]) for token, count in expected_counts.items()
    )
    missing = [
        token
        for token, count in expected_counts.items()
        for _ in range(max(0, count - extracted_counts[token]))
    ]
    return matched / expected_total, missing


def spaced_uppercase_lines(text: str) -> list[str]:
    """Find lines containing at least four isolated uppercase characters."""
    matches = []
    for line in text.splitlines():
        words = line.split()
        isolated = [word for word in words if len(word) == 1 and word.isupper()]
        if len(isolated) >= 4:
            matches.append(" ".join(words))
    return matches


def _vertical_overlap(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return max(0.0, min(first[3], second[3]) - max(first[1], second[1]))


def pages_with_parallel_columns(document: fitz.Document) -> list[int]:
    """Detect pages with text blocks occupying parallel left/right columns."""
    column_pages = []
    for page_number, page in enumerate(document, 1):
        width = page.rect.width
        blocks = [
            block
            for block in page.get_text("blocks", sort=False)
            if block[4].strip() and (block[2] - block[0]) < width * 0.65
        ]
        left = [block for block in blocks if (block[0] + block[2]) / 2 < width * 0.43]
        right = [block for block in blocks if (block[0] + block[2]) / 2 > width * 0.57]
        if any(
            _vertical_overlap(left_block, right_block)
            >= min(left_block[3] - left_block[1], right_block[3] - right_block[1])
            * 0.35
            for left_block in left
            for right_block in right
        ):
            column_pages.append(page_number)
    return column_pages


def repeated_top_lines(document: fitz.Document) -> list[str]:
    """Find normalized top-quarter lines repeated on every page."""
    if document.page_count < 2:
        return []

    page_lines: list[set[str]] = []
    for page in document:
        clip = fitz.Rect(0, 0, page.rect.width, page.rect.height * 0.25)
        normalized = {
            " ".join(line.split()).casefold()
            for line in page.get_text(clip=clip).splitlines()
            if len("".join(line.split())) >= 4
        }
        page_lines.append(normalized)
    return sorted(set.intersection(*page_lines))


def infer_html_path(pdf_path: Path, html_dir: Path | None) -> Path | None:
    """Map the standard generated PDF filename to its HTML counterpart."""
    if html_dir is None:
        return None
    # Prefer the longest matching output ID; candidate names are user-editable.
    candidates = sorted(
        html_dir.glob("*.html"), key=lambda p: len(p.stem), reverse=True
    )
    return next(
        (
            path
            for path in candidates
            if pdf_path.stem == path.stem or pdf_path.stem.endswith(f"_{path.stem}")
        ),
        None,
    )


def audit_pdf(
    path: Path,
    *,
    html_path: Path | None = None,
    max_size_mb: float = DEFAULT_MAX_SIZE_MB,
) -> AuditResult:
    """Audit one PDF without sending its contents to an external service."""
    findings: list[Finding] = []
    size_bytes = path.stat().st_size
    size_limit = int(max_size_mb * 1024 * 1024)
    if size_bytes > size_limit:
        findings.append(
            Finding(
                "error",
                "file-size",
                f"PDF exceeds the configured {max_size_mb:g} MB size threshold.",
                f"{size_bytes / 1024 / 1024:.2f} MB",
            )
        )

    with fitz.open(path) as document:
        page_texts = [page.get_text(sort=False) for page in document]
        pages = document.page_count
        extracted_text = "\n".join(page_texts)

        empty_pages = [
            index
            for index, text in enumerate(page_texts, 1)
            if len(re.sub(r"\W", "", text, flags=re.UNICODE)) < 30
        ]
        if empty_pages:
            findings.append(
                Finding(
                    "error",
                    "selectable-text",
                    "One or more pages contain little or no selectable text.",
                    f"pages: {', '.join(map(str, empty_pages))}",
                )
            )

        if "\ufffd" in extracted_text:
            findings.append(
                Finding(
                    "error",
                    "replacement-glyph",
                    "Extracted text contains Unicode replacement glyphs.",
                )
            )

        spaced_lines = spaced_uppercase_lines(extracted_text)
        if spaced_lines:
            findings.append(
                Finding(
                    "warning",
                    "spaced-text",
                    "Decorative letter spacing becomes separate characters in extraction.",
                    spaced_lines[0][:160],
                )
            )

        column_pages = pages_with_parallel_columns(document)
        if column_pages:
            findings.append(
                Finding(
                    "warning",
                    "parallel-columns",
                    "Parallel text columns make parser reading order implementation-dependent.",
                    f"pages: {', '.join(map(str, column_pages))}",
                )
            )

        repeated_lines = repeated_top_lines(document)
        if repeated_lines:
            findings.append(
                Finding(
                    "warning",
                    "repeated-top-content",
                    "Text repeated at the top of every page may be duplicated or treated as a header.",
                    "; ".join(repeated_lines[:3])[:200],
                )
            )

        image_pages = [
            page_number
            for page_number, page in enumerate(document, 1)
            if page.get_images(full=True)
        ]
        if image_pages:
            findings.append(
                Finding(
                    "warning",
                    "embedded-images",
                    "Embedded images are ignored by text extraction and are discouraged by some ATS guidance.",
                    f"pages: {', '.join(map(str, image_pages))}",
                )
            )

    recall = None
    if html_path is not None:
        expected_text = visible_html_text(html_path.read_text(encoding="utf-8"))
        recall, missing = token_recall(expected_text, extracted_text)
        severity: Severity | None
        if recall < ERROR_TOKEN_RECALL:
            severity = "error"
        elif recall < WARNING_TOKEN_RECALL:
            severity = "warning"
        else:
            severity = None
        if severity is not None:
            findings.append(
                Finding(
                    severity,
                    "html-token-recall",
                    "Some visible HTML tokens are missing from extracted PDF text.",
                    f"recall={recall:.1%}; missing={', '.join(missing[:12]) or 'none'}",
                )
            )

    return AuditResult(
        path=str(path),
        pages=pages,
        size_bytes=size_bytes,
        extracted_characters=len(extracted_text),
        html_token_recall=recall,
        findings=tuple(findings),
    )


def format_result(result: AuditResult) -> str:
    """Render a concise human-readable result."""
    recall = (
        f", HTML token recall {result.html_token_recall:.1%}"
        if result.html_token_recall is not None
        else ""
    )
    lines = [
        f"{result.path}: {result.pages} page(s), {result.size_bytes:,} bytes, "
        f"{result.extracted_characters:,} extracted characters{recall}"
    ]
    if not result.findings:
        lines.append("  PASS no compatibility risks detected by this probe")
    for finding in result.findings:
        line = f"  {finding.severity.upper():7s} {finding.code}: {finding.message}"
        if finding.evidence:
            line += f" [{finding.evidence}]"
        lines.append(line)
    return "\n".join(lines)


def default_pdf_paths(root: Path) -> list[Path]:
    return sorted((root / "output" / "pdf").glob("*.pdf"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(
        description="Run observable ATS-compatibility diagnostics (not an ATS score)."
    )
    parser.add_argument("pdfs", nargs="*", type=Path, help="PDFs to inspect")
    parser.add_argument(
        "--html-dir",
        type=Path,
        default=root / "output" / "html",
        help="directory containing matching generated HTML",
    )
    parser.add_argument("--max-size-mb", type=float, default=DEFAULT_MAX_SIZE_MB)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero for warnings as well as errors",
    )
    args = parser.parse_args(argv)
    if not args.pdfs:
        args.pdfs = default_pdf_paths(root)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    missing = [path for path in args.pdfs if not path.is_file()]
    if missing:
        for path in missing:
            print(f"PDF not found: {path}", file=sys.stderr)
        return 2
    if not args.pdfs:
        print("No PDFs found; run scripts/build.py first.", file=sys.stderr)
        return 2

    results = [
        audit_pdf(
            path,
            html_path=infer_html_path(path, args.html_dir),
            max_size_mb=args.max_size_mb,
        )
        for path in args.pdfs
    ]
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print("ATS compatibility probe (observable diagnostics, not an ATS score)\n")
        print("\n\n".join(format_result(result) for result in results))
        errors = sum(result.error_count for result in results)
        warnings = sum(result.warning_count for result in results)
        print(f"\nSummary: {errors} error(s), {warnings} warning(s)")

    errors = sum(result.error_count for result in results)
    warnings = sum(result.warning_count for result in results)
    return int(errors > 0 or (args.strict and warnings > 0))


if __name__ == "__main__":
    sys.exit(main())
