"""Application-overlay model, loading, transformation, and rendering coverage."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from data_loader import load_application_overlay
from models import ApplicationOverlay
from renderer import TemplateRenderer
from transforms import CVTransformer

PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLE_OVERLAY = PROJECT_ROOT / "data" / "applications" / "example-agent-builder.yaml"


def _overlay_data():
    return yaml.safe_load(EXAMPLE_OVERLAY.read_text())


def _write_overlay(tmp_path, data):
    path = tmp_path / "private-role.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_tracked_overlay_tailors_verified_content(real_cv_data):
    overlay = load_application_overlay(EXAMPLE_OVERLAY, real_cv_data)
    transformed = CVTransformer(real_cv_data).transform(
        "contracting",
        application=overlay,
    )

    assert transformed["personal_info"]["title"] == (
        "Senior Python Engineer & AI-Assisted Development"
    )
    assert transformed["skills"]["technical"][1]["label"] == ("AI-assisted development")
    assert [item["id"] for item in transformed["practice_evidence"]] == [
        "practice.ai.team-delivery-flow",
        "practice.ai.agent-parallelization",
        "practice.ai.deterministic-tools",
    ]
    commerce = next(
        item for item in transformed["experience"] if item["id"] == "commerce"
    )
    career_index = {
        item.id: item.statement for item in real_cv_data.career_evidence.items
    }
    assert commerce["achievements"] == [
        career_index["evidence.commerce.architecture-decisions"],
        career_index["evidence.commerce.product-planning"],
        career_index["evidence.commerce.quality-practices"],
    ]
    assert transformed["application"]["engagement_terms"]["capacity"] == (
        "Confirm for the specific application."
    )


def test_application_practice_renders_but_terms_do_not(real_cv_data):
    overlay = load_application_overlay(EXAMPLE_OVERLAY, real_cv_data)
    transformed = CVTransformer(real_cv_data).transform(
        "contracting",
        application=overlay,
    )
    html = TemplateRenderer(project_root=PROJECT_ROOT).render(
        "contracting",
        transformed,
    )

    assert "AI-Native Engineering" in html
    assert transformed["practice_evidence"][0]["statement"] in html
    assert "Confirm for the specific application." not in html


def test_external_overlay_path_uses_same_validation(real_cv_data, tmp_path):
    path = _write_overlay(tmp_path, _overlay_data())
    overlay = load_application_overlay(path, real_cv_data)
    assert overlay.output_id == "example-agent-builder"


def test_unknown_sidebar_reference_is_rejected(real_cv_data, tmp_path):
    data = _overlay_data()
    data["sidebar"]["selection"]["capabilities"] = ["capability.missing"]
    with pytest.raises(ValueError, match="unknown ID 'capability.missing'"):
        load_application_overlay(_write_overlay(tmp_path, data), real_cv_data)


def test_unknown_practice_evidence_is_rejected(real_cv_data, tmp_path):
    data = _overlay_data()
    data["practice_evidence_ids"] = ["practice.ai.missing"]
    with pytest.raises(ValueError, match="unknown practice evidence"):
        load_application_overlay(_write_overlay(tmp_path, data), real_cv_data)


def test_verified_private_evidence_is_rejected_when_loading(real_cv_data, tmp_path):
    data = _overlay_data()
    data["practice_evidence_ids"] = ["practice.ai.feature-throughput"]
    with pytest.raises(ValueError, match="is private"):
        load_application_overlay(_write_overlay(tmp_path, data), real_cv_data)


def test_verified_private_evidence_cannot_bypass_loader(real_cv_data):
    data = _overlay_data()
    data["practice_evidence_ids"] = ["practice.ai.feature-throughput"]
    overlay = ApplicationOverlay(**data)
    with pytest.raises(ValueError, match="is private"):
        CVTransformer(real_cv_data).transform("contracting", application=overlay)


def test_non_verified_career_evidence_is_rejected(real_cv_data, tmp_path):
    data = _overlay_data()
    data["career_evidence"][0]["evidence_ids"] = ["evidence.commerce.on-time-delivery"]
    with pytest.raises(ValueError, match="must be verified, not 'candidate'"):
        load_application_overlay(_write_overlay(tmp_path, data), real_cv_data)


def test_cross_record_career_evidence_is_rejected(real_cv_data, tmp_path):
    data = _overlay_data()
    data["career_evidence"][0]["evidence_ids"] = ["evidence.consulting.rest-apis"]
    with pytest.raises(ValueError, match="belongs to 'consulting', not 'commerce'"):
        load_application_overlay(_write_overlay(tmp_path, data), real_cv_data)


def test_invalid_application_variant_edition_is_rejected():
    data = _overlay_data()
    data["target"] = {"variant": "contracting", "edition": "extended"}
    with pytest.raises(ValidationError, match="edition is unsupported"):
        ApplicationOverlay(**data)


def test_application_target_mismatch_is_rejected(real_cv_data):
    overlay = load_application_overlay(EXAMPLE_OVERLAY, real_cv_data)
    with pytest.raises(ValueError, match="targets variant 'contracting'"):
        CVTransformer(real_cv_data).transform("employment", application=overlay)


def test_output_id_requires_safe_kebab_case():
    data = _overlay_data()
    data["output_id"] = "../private role"
    with pytest.raises(ValidationError, match="lowercase kebab-case"):
        ApplicationOverlay(**data)
