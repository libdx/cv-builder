#!/usr/bin/env python3
"""
CV build pipeline — the single entry point.

Load → Validate → Transform → Render (HTML/PDF/DOCX).

Usage:
    python scripts/build.py                      # all variants, HTML + PDF + DOCX
    python scripts/build.py --variant freelance  # one variant
    python scripts/build.py --variant freelance --edition extended
    python scripts/build.py --application data/applications/example-agent-builder.yaml
    python scripts/build.py --format html        # skip PDF (fast iteration)
    python scripts/build.py --format pdf         # PDF only
    python scripts/build.py --format docx        # editable Word document only

Exit codes:
    0 success, 1 failure (validation or unknown variant).
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_loader import load_application_overlay, load_cv_data
from models import ApplicationOverlay, EditionType, VariantType
from transforms import CVTransformer
from renderer import TemplateRenderer

VARIANTS: list[VariantType] = ["employment", "contracting", "freelance"]


def candidate_prefix(personal_info) -> str:
    """Derive a filesystem-safe basename from the current candidate identity."""
    name = f"{personal_info.first_name}_{personal_info.last_name}".lower()
    return re.sub(r"[^\w-]+", "_", name, flags=re.UNICODE).strip("_-") or "cv"


def build(
    variants: list[VariantType],
    fmt: str,
    root: Path,
    edition: Optional[EditionType] = None,
    application_path: Optional[Path] = None,
) -> int:
    html_dir = root / "output" / "html"
    pdf_dir = root / "output" / "pdf"
    docx_dir = root / "output" / "docx"

    # Load + validate
    application: Optional[ApplicationOverlay] = None
    try:
        cv_data = load_cv_data(root)
        if application_path is not None:
            application = load_application_overlay(application_path, cv_data)
    except FileNotFoundError as e:
        print(f"✗ Data file not found: {e.filename}")
        return 1
    except ValidationError as e:
        print("✗ Data validation failed:")
        print(e)
        return 1
    except (ValueError, yaml.YAMLError) as e:
        print(f"✗ Data loading failed: {e}")
        return 1

    if application is not None:
        if not variants:
            variants = [application.target.variant]
        if variants != [application.target.variant]:
            print(
                f"✗ Application '{application.id}' targets --variant "
                f"{application.target.variant}"
            )
            return 1
        if edition is None:
            edition = application.target.edition
        elif edition != application.target.edition:
            print(
                f"✗ Application '{application.id}' targets --edition "
                f"{application.target.edition}"
            )
            return 1
    elif not variants:
        variants = VARIANTS

    if edition is not None and variants != ["freelance"]:
        print("✗ --edition is only supported with --variant freelance")
        return 1

    transformer = CVTransformer(cv_data)
    filename_prefix = candidate_prefix(cv_data.personal_info)

    # HTML rendering is shared by HTML and PDF, but a DOCX-only build does
    # not need Jinja templates or Chromium.
    renderer = (
        TemplateRenderer(project_root=root) if fmt in ("html", "pdf", "all") else None
    )

    # PDF generator is imported lazily so HTML-only builds don't require
    # Playwright/Chromium to be installed.
    pdf_generator = None
    if fmt in ("pdf", "all"):
        from generator import PDFGenerator

        pdf_generator = PDFGenerator()

    docx_generator = None
    if fmt in ("docx", "all"):
        from docx_generator import DocxGenerator

        docx_generator = DocxGenerator(project_root=root)

    for variant in variants:
        data = transformer.transform(
            variant,
            edition=edition,
            application=application,
        )
        html = renderer.render(variant, data) if renderer is not None else None
        output_name = (
            application.output_id
            if application is not None
            else (
                f"{variant}_{data['edition']}"
                if data["edition"] is not None
                else variant
            )
        )

        if fmt in ("html", "all"):
            assert html is not None
            html_dir.mkdir(parents=True, exist_ok=True)
            html_file = html_dir / f"{output_name}.html"
            html_file.write_text(html)
            print(
                f"✓ HTML  {variant:12s} → {html_file.relative_to(root)} ({len(html):,} B)"
            )

        if fmt in ("pdf", "all"):
            assert pdf_generator is not None
            assert html is not None
            pdf_file = pdf_dir / f"{filename_prefix}_{output_name}.pdf"
            pdf_generator.generate(html, pdf_file)
            size = pdf_file.stat().st_size
            print(f"✓ PDF   {variant:12s} → {pdf_file.relative_to(root)} ({size:,} B)")

        if fmt in ("docx", "all"):
            assert docx_generator is not None
            docx_file = docx_dir / f"{filename_prefix}_{output_name}.docx"
            docx_generator.generate(data, docx_file)
            size = docx_file.stat().st_size
            print(
                f"✓ DOCX  {variant:12s} → "
                f"{docx_file.relative_to(root)} ({size:,} B)"
            )

    print(f"\n✓ Built {len(variants)} variant(s) [{fmt}]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build CV variants.")
    parser.add_argument("--variant", choices=VARIANTS + ["all"])
    parser.add_argument("--edition", choices=["concise", "extended"])
    parser.add_argument(
        "--application",
        type=Path,
        help="Tracked sanitized or external private application-overlay YAML",
    )
    parser.add_argument(
        "--format", choices=["html", "pdf", "docx", "all"], default="all"
    )
    args = parser.parse_args()

    if args.application is not None and args.variant == "all":
        parser.error("--application cannot be combined with --variant all")
    if (
        args.application is None
        and args.edition is not None
        and args.variant != "freelance"
    ):
        parser.error("--edition is only supported with --variant freelance")

    variants = (
        VARIANTS
        if args.variant == "all"
        else [args.variant] if args.variant is not None else []
    )
    root = Path(__file__).parent.parent
    return build(
        variants,
        args.format,
        root,
        edition=args.edition,
        application_path=args.application,
    )


if __name__ == "__main__":
    sys.exit(main())
