"""Unit coverage for layered audience, edition, and overlay transformation."""

import copy

import pytest

from models import CVData, CareerPresentationRule
from transforms import CVTransformer, TransformPipeline


def _verified_evidence(record_id, suffix, kind, statement):
    return {
        "id": f"evidence.{record_id}.{suffix}",
        "career_record_id": record_id,
        "kind": kind,
        "state": "verified",
        "statement": statement,
        "provenance": [
            {"source": "candidate_direct_experience", "reference": "test fixture"}
        ],
        "verification_note": "Confirmed for the fixture.",
    }


@pytest.fixture
def cv_data(minimal_cv_dict, make_experience):
    """Controlled records plus sparse policy exceptions for every layer."""
    data = copy.deepcopy(minimal_cv_dict)
    data["profile"]["contracting"] = data["profile"]["employment"]
    data["experience"] = [
        make_experience(
            "recent",
            company="Named Client",
            company_anonymous="Product SaaS platform",
            relationship="freelance_contract",
        ),
        make_experience("mid", company="Example Consulting"),
        make_experience("old", company="Example Learning"),
    ]
    data["career_policy"]["variants"]["freelance"]["rules"].append(
        {
            "match": {"id": "mid"},
            "set": {
                "representation": "position",
                "placement": "prior_employment",
                "identity": "named",
                "detail": "compact",
                "order": 1,
            },
        }
    )
    return CVData(**data)


class TestAudienceRules:
    def test_employment_keeps_canonical_order_and_named_positions(self, cv_data):
        result = CVTransformer(cv_data).transform("employment")
        assert [item["id"] for item in result["experience"]] == [
            "recent",
            "mid",
            "old",
        ]
        assert result["experience"][0]["company"] == "Named Client"

    def test_contracting_resolves_content_identically_to_employment(self, cv_data):
        transformer = CVTransformer(cv_data)
        employment = transformer.transform("employment")
        contracting = transformer.transform("contracting")
        assert contracting["profile"] == employment["profile"]
        assert contracting["experience"] == employment["experience"]
        assert (
            contracting["resolved_presentations"]
            == employment["resolved_presentations"]
        )

    def test_freelance_uses_engagement_and_prior_employment_groups(self, cv_data):
        result = CVTransformer(cv_data).transform("freelance")
        assert [item["id"] for item in result["engagements"]] == ["recent"]
        assert result["engagements"][0]["context"] == "Product SaaS platform"
        assert [item["id"] for item in result["prior_employment"]] == ["mid"]
        assert result["experience"] == []

    def test_anonymous_identity_requires_a_safe_label(
        self, minimal_cv_dict, make_experience
    ):
        data = copy.deepcopy(minimal_cv_dict)
        data["experience"] = [
            make_experience(
                "client",
                company_anonymous=None,
                relationship="freelance_contract",
            )
        ]
        with pytest.raises(ValueError, match="safe anonymous label"):
            CVTransformer(CVData(**data)).transform("freelance")


class TestOrdering:
    def test_external_order_overrides_inventory_order(
        self, minimal_cv_dict, make_experience
    ):
        data = copy.deepcopy(minimal_cv_dict)
        data["experience"] = [make_experience("third"), make_experience("first")]
        data["career_policy"]["variants"]["employment"]["rules"].extend(
            [
                {"match": {"id": "third"}, "set": {"order": 30}},
                {"match": {"id": "first"}, "set": {"order": 10}},
            ]
        )
        result = CVTransformer(CVData(**data)).transform("employment")
        assert [item["id"] for item in result["experience"]] == ["first", "third"]


class TestEvidenceRendering:
    def test_one_evidence_item_is_reused_between_representations(
        self, minimal_cv_dict, make_experience
    ):
        data = copy.deepcopy(minimal_cv_dict)
        data["experience"] = [
            make_experience("client", relationship="freelance_contract")
        ]
        item = _verified_evidence(
            "client", "delivery", "contribution", "Delivered a verified system."
        )
        data["career_evidence"]["items"] = [item]
        data["experience"][0]["evidence_ids"] = [item["id"]]
        cv = CVData(**data)
        transformer = CVTransformer(cv)

        employment = transformer.transform("employment")["experience"][0]
        freelance = transformer.transform("freelance")["engagements"][0]

        assert employment["achievements"] == [item["statement"]]
        assert freelance["contributions"] == [item["statement"]]
        assert item["statement"] not in data["experience"][0]

    def test_concise_and_extended_apply_different_verified_depth(
        self, minimal_cv_dict, make_experience
    ):
        data = copy.deepcopy(minimal_cv_dict)
        data["experience"] = [
            make_experience("client", relationship="freelance_contract")
        ]
        items = [
            _verified_evidence(
                "client",
                f"contribution-{number}",
                "contribution",
                f"Contribution {number}.",
            )
            for number in range(1, 4)
        ]
        data["career_evidence"]["items"] = items
        data["experience"][0]["evidence_ids"] = [item["id"] for item in items]
        transformer = CVTransformer(CVData(**data))

        concise = transformer.transform("freelance")["engagements"][0]
        extended = transformer.transform("freelance", edition="extended")[
            "engagements"
        ][0]

        assert concise["contributions"] == ["Contribution 1.", "Contribution 2."]
        assert extended["contributions"] == [
            "Contribution 1.",
            "Contribution 2.",
            "Contribution 3.",
        ]

    def test_defensive_boundary_excludes_non_verified_state(
        self, minimal_cv_dict, make_experience
    ):
        data = copy.deepcopy(minimal_cv_dict)
        data["experience"] = [
            make_experience("client", relationship="freelance_contract")
        ]
        item = _verified_evidence(
            "client", "delivery", "outcome", "Must not render after mutation."
        )
        data["career_evidence"]["items"] = [item]
        data["experience"][0]["evidence_ids"] = [item["id"]]
        cv = CVData(**data)
        cv.career_evidence.items[0].state = "candidate"

        result = CVTransformer(cv).transform("freelance")
        assert result["engagements"][0]["outcomes"] == []


class TestEditionAndOverlayPrecedence:
    def test_freelance_defaults_to_concise(self, cv_data):
        result = CVTransformer(cv_data).transform("freelance")
        assert result["edition"] == "concise"

    def test_non_freelance_edition_is_rejected(self, cv_data):
        with pytest.raises(ValueError, match="only available with freelance"):
            CVTransformer(cv_data).transform("employment", edition="extended")

    def test_overlay_applies_after_edition_using_generic_properties(self, cv_data):
        overlay = CareerPresentationRule(
            match={"id": "recent"},
            set={
                "representation": "position",
                "placement": "selected_experience",
                "identity": "named",
                "detail": "compact",
                "order": 1,
            },
        )
        result = CVTransformer(cv_data).transform(
            "freelance",
            edition="extended",
            application_rules=[overlay],
        )

        assert result["engagements"] == []
        assert result["selected_experience"][0]["company"] == "Named Client"
        diagnostic = next(
            item for item in result["resolved_presentations"] if item["id"] == "recent"
        )
        assert set(diagnostic["sources"].values()) == {"application_overlay"}

    def test_partial_reveal_rejects_position_in_engagement_placement(self, cv_data):
        incomplete_reveal = CareerPresentationRule(
            match={"id": "recent"},
            set={"representation": "position", "identity": "named"},
        )

        with pytest.raises(
            ValueError,
            match="position.*cannot use placement 'consultancy_engagements'",
        ):
            CVTransformer(cv_data).transform(
                "freelance",
                application_rules=[incomplete_reveal],
            )

    def test_engagement_rejects_position_only_placement(self, cv_data):
        invalid_engagement = CareerPresentationRule(
            match={"id": "mid"},
            set={"representation": "engagement"},
        )

        with pytest.raises(
            ValueError,
            match="engagement.*cannot use placement 'prior_employment'",
        ):
            CVTransformer(cv_data).transform(
                "freelance",
                application_rules=[invalid_engagement],
            )

    def test_named_reveal_sets_required_generic_properties(self, cv_data):
        reveal = CareerPresentationRule(
            match={"id": "recent"},
            set={
                "representation": "position",
                "placement": "selected_experience",
                "identity": "named",
            },
        )

        result = CVTransformer(cv_data).transform(
            "freelance",
            edition="extended",
            application_rules=[reveal],
        )

        revealed = result["selected_experience"][0]
        assert revealed["id"] == "recent"
        assert revealed["company"] == "Named Client"
        assert result["engagements"] == []
        diagnostic = next(
            item for item in result["resolved_presentations"] if item["id"] == "recent"
        )
        assert diagnostic["sources"]["representation"] == "application_overlay"
        assert diagnostic["sources"]["placement"] == "application_overlay"
        assert diagnostic["sources"]["identity"] == "application_overlay"
        assert diagnostic["sources"]["detail"] == "edition:freelance_extended"

    def test_partial_overlay_can_change_identity_without_changing_representation(
        self, cv_data
    ):
        reveal_identity = CareerPresentationRule(
            match={"id": "recent"},
            set={"identity": "named"},
        )

        result = CVTransformer(cv_data).transform(
            "freelance", application_rules=[reveal_identity]
        )
        assert result["engagements"][0]["context"] == "Named Client"


class TestSharedAndSidebarSections:
    def test_shared_sections_present(self, cv_data):
        result = CVTransformer(cv_data).transform("employment")
        assert result["contact"]["email"] == "test@example.com"
        assert result["skills"]["technical"] == [
            {"label": "Backend", "items": ["Python"]}
        ]
        assert result["skills"]["capabilities"] == ["Technical leadership"]

    def test_freelance_extended_moves_languages_to_continuation(self, cv_data):
        result = CVTransformer(cv_data).transform("freelance", edition="extended")
        languages = next(
            section for section in result["sidebar"] if section["id"] == "languages"
        )
        assert languages["placement"] == "sidebar_continuation"


class TestPipeline:
    def test_transform_all_returns_three_default_outputs(self, cv_data):
        results = TransformPipeline(cv_data).transform_all()
        assert set(results) == {"employment", "contracting", "freelance"}
        assert results["freelance"]["edition"] == "concise"
