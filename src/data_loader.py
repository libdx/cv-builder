"""Load the current canonical CV plus external sidebar inventory and policy."""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from models import ApplicationOverlay, CVData


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load one YAML mapping, preserving the failing path in errors."""
    with path.open("r") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def load_cv_data(
    project_root: Path,
    canonical_path: Optional[Path] = None,
) -> CVData:
    """Compose layered sidebar and career evidence inputs, then validate."""
    canonical_path = canonical_path or project_root / "data" / "cv_data.yaml"
    raw_data = _load_yaml(canonical_path)

    selection = raw_data.get("sidebar")
    if not isinstance(selection, dict):
        raise ValueError(f"Missing canonical sidebar selection in {canonical_path}")

    raw_data["sidebar"] = {
        "inventory": _load_yaml(
            project_root / "data" / "inventory" / "attributes.yaml"
        ),
        "selection": selection,
        "policy": _load_yaml(project_root / "data" / "policies" / "sidebar.yaml"),
    }
    raw_data["career_evidence"] = _load_yaml(
        project_root / "data" / "inventory" / "career-evidence.yaml"
    )
    raw_data["practice_evidence"] = _load_yaml(
        project_root / "data" / "inventory" / "practice-evidence.yaml"
    )
    raw_data["career_policy"] = _load_yaml(
        project_root / "data" / "policies" / "career.yaml"
    )
    return CVData(**raw_data)


def load_application_overlay(path: Path, cv_data: CVData) -> ApplicationOverlay:
    """Load one sparse application overlay and validate canonical references."""
    overlay = ApplicationOverlay(**_load_yaml(path))
    _validate_application_references(overlay, cv_data)
    return overlay


def _validate_application_references(
    overlay: ApplicationOverlay,
    cv_data: CVData,
) -> None:
    sidebar_collections = {
        "technical_skill_groups": cv_data.sidebar.inventory.technical_skill_groups,
        "capabilities": cv_data.sidebar.inventory.capabilities,
        "languages": cv_data.sidebar.inventory.languages,
        "interests": cv_data.sidebar.inventory.interests,
    }
    for field_name, items in sidebar_collections.items():
        selected = getattr(overlay.sidebar.selection, field_name)
        if selected is None:
            continue
        index = {item.id: item for item in items}
        for item_id in selected:
            item = index.get(item_id)
            if item is None:
                raise ValueError(
                    f"Application sidebar selection references unknown ID "
                    f"'{item_id}'"
                )
            if item.state != "verified":
                raise ValueError(
                    f"Application sidebar selection '{item_id}' must reference "
                    "verified inventory"
                )

    experience_ids = {experience.id for experience in cv_data.experience}
    for rule in overlay.career_presentation:
        record_id = rule.match.id
        if record_id is not None and record_id not in experience_ids:
            raise ValueError(
                f"Application presentation rule references unknown record "
                f"'{record_id}'"
            )

    career_index = {item.id: item for item in cv_data.career_evidence.items}
    for selection in overlay.career_evidence:
        if selection.record_id not in experience_ids:
            raise ValueError(
                f"Application career evidence references unknown record "
                f"'{selection.record_id}'"
            )
        selected_ids = selection.evidence_ids or []
        if "summary_evidence_id" in selection.model_fields_set:
            selected_ids = [*selected_ids, selection.summary_evidence_id]
        for evidence_id in selected_ids:
            if evidence_id is None:
                continue
            item = career_index.get(evidence_id)
            if item is None:
                raise ValueError(
                    f"Application career selection references unknown evidence "
                    f"'{evidence_id}'"
                )
            if item.career_record_id != selection.record_id:
                raise ValueError(
                    f"Application evidence '{evidence_id}' belongs to "
                    f"'{item.career_record_id}', not '{selection.record_id}'"
                )
            if item.state != "verified":
                raise ValueError(
                    f"Application evidence '{evidence_id}' must be verified, "
                    f"not '{item.state}'"
                )

    practice_index = {item.id: item for item in cv_data.practice_evidence.items}
    for evidence_id in overlay.practice_evidence_ids:
        item = practice_index.get(evidence_id)
        if item is None:
            raise ValueError(
                f"Application references unknown practice evidence '{evidence_id}'"
            )
        if item.disclosure != "external":
            raise ValueError(
                f"Application practice evidence '{evidence_id}' is private "
                "and is not approved for external use"
            )
        if item.state != "verified":
            raise ValueError(
                f"Application practice evidence '{evidence_id}' must be verified, "
                f"not '{item.state}'"
            )
