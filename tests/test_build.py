"""CLI integration coverage for edition selection and output naming."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build.py"


@pytest.mark.parametrize("edition", ["concise", "extended"])
def test_cli_builds_edition_specific_html(edition):
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--variant",
            "freelance",
            "--edition",
            edition,
            "--format",
            "html",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = PROJECT_ROOT / "output" / "html" / f"freelance_{edition}.html"
    assert result.returncode == 0, result.stderr or result.stdout
    assert output.is_file()
    assert f"cv-edition-{edition}" in output.read_text()


def test_cli_defaults_freelance_to_concise_filename():
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--variant",
            "freelance",
            "--format",
            "html",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "output/html/freelance_concise.html" in result.stdout


def test_cli_builds_application_specific_html():
    application = PROJECT_ROOT / "data" / "applications" / "example-agent-builder.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--application",
            str(application),
            "--format",
            "html",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = PROJECT_ROOT / "output" / "html" / "example-agent-builder.html"
    assert result.returncode == 0, result.stderr or result.stdout
    assert output.is_file()
    assert "Senior Python Engineer &amp; AI-Assisted Development" in output.read_text()


@pytest.mark.skipif(
    importlib.util.find_spec("docx") is None,
    reason="python-docx is not installed",
)
def test_cli_builds_edition_specific_docx():
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--variant",
            "freelance",
            "--edition",
            "extended",
            "--format",
            "docx",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = PROJECT_ROOT / "output" / "docx" / "joe_doe_freelance_extended.docx"
    assert result.returncode == 0, result.stderr or result.stdout
    assert output.is_file()
    assert "output/docx/joe_doe_freelance_extended.docx" in result.stdout


def test_cli_rejects_application_variant_mismatch():
    application = PROJECT_ROOT / "data" / "applications" / "example-agent-builder.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--application",
            str(application),
            "--variant",
            "employment",
            "--format",
            "html",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "targets --variant contracting" in result.stdout


@pytest.mark.parametrize("variant", ["employment", "contracting", "all"])
def test_cli_rejects_edition_for_unsupported_variant(variant):
    result = subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--variant",
            variant,
            "--edition",
            "extended",
            "--format",
            "html",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--edition is only supported with --variant freelance" in result.stderr
