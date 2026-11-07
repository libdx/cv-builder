"""User identity changes must propagate to exports and diagnostics."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build import build, candidate_prefix
from ats_check import infer_html_path


def test_export_uses_current_identity_without_path_traversal(tmp_path):
    assert (
        candidate_prefix(SimpleNamespace(first_name="../Jane", last_name="Smith/.."))
        == "jane_smith"
    )


def test_custom_candidate_docx_filename(tmp_path):
    import shutil
    import yaml

    root = Path(__file__).parent.parent
    shutil.copytree(root / "data", tmp_path / "data")
    data_path = tmp_path / "data/cv_data.yaml"
    data = yaml.safe_load(data_path.read_text())
    data["personal_info"].update(first_name="Jane", last_name="Smith", photo=None)
    data_path.write_text(yaml.safe_dump(data))
    assert build(["employment"], "docx", tmp_path) == 0
    assert (tmp_path / "output/docx/jane_smith_employment.docx").is_file()


def test_ats_matches_custom_name_and_longest_output_id(tmp_path):
    (tmp_path / "extended.html").touch()
    expected = tmp_path / "freelance_extended.html"
    expected.touch()
    assert (
        infer_html_path(Path("jane_smith_freelance_extended.pdf"), tmp_path) == expected
    )
    assert infer_html_path(Path("unmatched.pdf"), tmp_path) is None
