"""
Tests for src/models.py — Pydantic data validation.
"""

import copy

import pytest
from pydantic import ValidationError

from models import CVData, CareerEvidenceItem, Education, PracticeEvidenceItem


class TestCVDataValid:
    """A well-formed payload validates cleanly."""

    def test_minimal_payload_validates(self, minimal_cv_dict):
        cv = CVData(**minimal_cv_dict)
        assert cv.personal_info.first_name == "Test"
        assert len(cv.experience) == 1

    def test_all_three_profiles_required(self, minimal_cv_dict):
        for variant in ("employment", "contracting", "freelance"):
            broken = copy.deepcopy(minimal_cv_dict)
            del broken["profile"][variant]
            with pytest.raises(ValidationError, match=variant):
                CVData(**broken)

    def test_empty_profile_text_rejected(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["profile"]["freelance"] = "   "
        with pytest.raises(ValidationError, match="freelance"):
            CVData(**broken)

    def test_duplicate_experience_ids_rejected(self, minimal_cv_dict, make_experience):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["experience"] = [make_experience("dup"), make_experience("dup")]
        with pytest.raises(ValidationError, match="unique"):
            CVData(**broken)

    def test_sidebar_selection_rejects_unknown_inventory_id(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["sidebar"]["selection"]["languages"] = ["language.unknown"]
        with pytest.raises(ValidationError, match="unknown ID"):
            CVData(**broken)

    def test_sidebar_selection_requires_verified_inventory(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["sidebar"]["inventory"]["languages"][0]["state"] = "candidate"
        with pytest.raises(ValidationError, match="verified inventory"):
            CVData(**broken)

    def test_sidebar_inventory_ids_are_globally_unique(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["sidebar"]["inventory"]["capabilities"][0]["id"] = "skill-group.backend"
        broken["sidebar"]["selection"]["capabilities"] = ["skill-group.backend"]
        with pytest.raises(ValidationError, match="globally unique"):
            CVData(**broken)


class TestCareerPolicyValidation:
    """External career-policy invariants."""

    def test_all_detail_levels_are_required(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        del broken["career_policy"]["details"]["extended"]
        with pytest.raises(ValidationError, match="compact, standard, and extended"):
            CVData(**broken)

    def test_edition_key_must_match_context(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["career_policy"]["editions"]["wrong_key"] = broken["career_policy"][
            "editions"
        ].pop("freelance_extended")
        with pytest.raises(ValidationError, match="must match"):
            CVData(**broken)

    def test_rule_match_cannot_be_empty(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["career_policy"]["variants"]["employment"]["rules"][0]["match"] = {}
        with pytest.raises(ValidationError, match="match cannot be empty"):
            CVData(**broken)

    def test_rule_cannot_reference_unknown_record(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        broken["career_policy"]["variants"]["employment"]["rules"].append(
            {"match": {"id": "missing"}, "set": {"order": 2}}
        )
        with pytest.raises(ValidationError, match="unknown record 'missing'"):
            CVData(**broken)


class TestCareerEvidenceValidation:
    """Evidence lifecycle and canonical selection invariants."""

    @staticmethod
    def _item(state="verified", career_record_id="job1"):
        item = {
            "id": f"evidence.{career_record_id}.delivery",
            "career_record_id": career_record_id,
            "kind": "contribution",
            "state": state,
            "statement": "Shipped a feature.",
            "provenance": [
                {
                    "source": "candidate_direct_experience",
                    "reference": "test fixture",
                }
            ],
            "verification_note": "Confirmed for the fixture.",
        }
        if state in {"retired", "rejected"}:
            item["state_reason"] = "Not eligible for canonical rendering."
        return item

    @pytest.mark.parametrize("state", ["candidate", "verified", "rejected"])
    def test_evidence_requires_provenance(self, state):
        item = self._item(state=state)
        item["provenance"] = []
        with pytest.raises(ValidationError, match="requires provenance"):
            CareerEvidenceItem(**item)

    def test_rejected_evidence_requires_reason(self):
        item = self._item(state="rejected")
        del item["state_reason"]
        with pytest.raises(ValidationError, match="requires a reason"):
            CareerEvidenceItem(**item)

    @pytest.mark.parametrize("state", ["candidate", "retired", "rejected"])
    def test_canonical_selection_rejects_non_verified_evidence(
        self, minimal_cv_dict, state
    ):
        broken = copy.deepcopy(minimal_cv_dict)
        item = self._item(state=state)
        broken["career_evidence"]["items"] = [item]
        broken["experience"][0]["evidence_ids"] = [item["id"]]
        with pytest.raises(ValidationError, match="must be verified"):
            CVData(**broken)

    def test_canonical_selection_rejects_cross_record_evidence(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        item = self._item(career_record_id="other")
        broken["experience"].append(
            {
                **broken["experience"][0],
                "id": "other",
            }
        )
        broken["career_evidence"]["items"] = [item]
        broken["experience"][0]["evidence_ids"] = [item["id"]]
        with pytest.raises(ValidationError, match="belongs to 'other'"):
            CVData(**broken)


class TestPracticeEvidenceValidation:
    """Cross-career practice evidence lifecycle invariants."""

    @staticmethod
    def _item(state="verified"):
        item = {
            "id": "practice.ai.agentic-workflows",
            "kind": "workflow",
            "state": state,
            "statement": "Use reviewable agentic engineering workflows.",
            "provenance": [
                {
                    "source": "candidate_direct_experience",
                    "reference": "test fixture",
                }
            ],
            "verification_note": "Confirmed for the fixture.",
        }
        if state in {"retired", "rejected"}:
            item["state_reason"] = "Not eligible for application copy."
        return item

    def test_verified_practice_validates(self):
        item = PracticeEvidenceItem(**self._item())
        assert item.state == "verified"

    def test_practice_id_requires_namespace(self):
        item = self._item()
        item["id"] = "ai.agentic-workflows"
        with pytest.raises(ValidationError, match="must start with 'practice.'"):
            PracticeEvidenceItem(**item)

    def test_verified_practice_requires_note(self):
        item = self._item()
        del item["verification_note"]
        with pytest.raises(ValidationError, match="requires a verification note"):
            PracticeEvidenceItem(**item)

    def test_duplicate_practice_ids_rejected(self, minimal_cv_dict):
        broken = copy.deepcopy(minimal_cv_dict)
        item = self._item()
        broken["practice_evidence"]["items"] = [item, item]
        with pytest.raises(ValidationError, match="globally unique"):
            CVData(**broken)


class TestEducationValidation:
    """Education year invariants."""

    def test_end_year_before_start_year_rejected(self):
        with pytest.raises(ValidationError, match="end_year"):
            Education(
                degree="BSc",
                institution="Uni",
                start_year=2015,
                end_year=2010,
            )

    def test_valid_year_range_accepted(self):
        edu = Education(
            degree="BSc",
            institution="Uni",
            start_year=2010,
            end_year=2014,
        )
        assert edu.end_year == 2014
