"""
Integration tests — the real pipeline against the real cv_data.yaml.

These complement the unit tests (which use synthetic fixtures): they assert
that the actual CV content renders correctly per variant, end to end,
through transform → render. No browser required.
"""

import re


def _count(html: str, needle: str) -> int:
    return html.count(needle)


class TestPipelineRenders:
    def test_all_variants_produce_html(self, rendered_html):
        for variant, html in rendered_html.items():
            assert html.lstrip().startswith("<!DOCTYPE html>"), variant
            assert "Joe" in html and "Doe" in html

    def test_self_contained(self, rendered_html):
        """CSS inlined and photo embedded — no external asset references."""
        for variant, html in rendered_html.items():
            assert "data:image/jpeg;base64," in html, f"{variant}: photo not embedded"
            assert ".cv-page" in html, f"{variant}: CSS not inlined"
            assert "<link" not in html, f"{variant}: unexpected external link"
            assert "https://https://" not in html, f"{variant}: malformed contact URL"


class TestVariantContent:
    def test_employment_shows_all_real_companies(self, rendered_html):
        html = rendered_html["employment"]
        assert _count(html, 'class="job"') == 7
        assert "Example Commerce" in html
        assert "Example Learning" in html  # employment-only role present

    def test_contracting_matches_employment_career_content(self, real_cv_data):
        from transforms import CVTransformer

        transformer = CVTransformer(real_cv_data)
        employment = transformer.transform("employment")
        contracting = transformer.transform("contracting")

        assert contracting["profile"] == employment["profile"]
        assert contracting["experience"] == employment["experience"]
        assert (
            contracting["resolved_presentations"]
            == employment["resolved_presentations"]
        )
        assert len(contracting["experience"]) == 7
        assert any(
            item["company"] == "Example Learning" for item in contracting["experience"]
        )

    def test_contracting_renders_all_shared_roles(self, rendered_html):
        html = rendered_html["contracting"]
        assert _count(html, 'class="job"') == 7
        assert "Example Learning" in html
        assert "Example Commerce" in html

    def test_contracting_labels_relationship_without_changing_role_titles(
        self, rendered_html, real_cv_data
    ):
        from html import unescape

        from transforms import CVTransformer

        jobs = CVTransformer(real_cv_data).transform("contracting")["experience"]
        metadata = re.findall(
            r'<div class="job__meta">(.*?)</div>',
            rendered_html["contracting"],
            re.DOTALL,
        )
        canonical = {item.id: item for item in real_cv_data.experience}
        assert len(metadata) == len(jobs)
        for job, meta in zip(jobs, metadata):
            assert job["title"] == canonical[job["id"]].title
            assert job["relationship"] == canonical[job["id"]].relationship
            assert job["company"] in unescape(meta)
            assert ("Independent Contractor" in meta) == (
                job["relationship"] == "freelance_contract"
            )
        assert "Independent Contractor" not in rendered_html["employment"]
        assert "Independent Contractor" not in rendered_html["freelance"]

    def test_freelance_default_is_concise_consultancy(self, rendered_html):
        html = rendered_html["freelance"]
        assert 'class="cv-freelance cv-edition-concise"' in html
        assert _count(html, 'class="engagement"') == 2
        assert "Example Commerce" not in html
        assert "Example Analytics" not in html
        assert "Commerce SaaS platform" in html
        assert "Reporting and analytics platform" in html
        assert "Confidential" not in html
        assert "Independent Backend Consultant" in html
        assert "Selected Client Engagements" in html
        assert "Example Consulting" in html
        assert "Example Workflow" not in html

    def test_both_freelance_editions_render_approved_structure(
        self, freelance_editions_html
    ):
        for edition, html in freelance_editions_html.items():
            assert f"cv-edition-{edition}" in html
            assert "Selected Client Engagements" in html
            assert "Scope" in html
            assert "Contributions" in html
            assert "Technologies" in html
            assert "Outcomes" in html
            assert "Confidential" not in html

    def test_engagements_are_undated_and_not_employment_entries(
        self, freelance_editions_html
    ):
        for html in freelance_editions_html.values():
            engagement_section = html.split("Selected Client Engagements", 1)[1].split(
                "Selected Prior Employment", 1
            )[0]
            assert "Senior Software Engineer" not in engagement_section
            assert "Senior Software Engineer" not in engagement_section
            assert "2022" not in engagement_section
            assert "2021" not in engagement_section

    def test_extended_adds_depth_and_earlier_credibility(self, freelance_editions_html):
        concise = freelance_editions_html["concise"]
        extended = freelance_editions_html["extended"]
        assert "Example Workflow" not in concise
        assert "Earlier Software Engineering" not in concise
        assert "Example Workflow" in extended
        assert "Earlier Software Engineering" in extended
        assert "Example Services" in extended
        assert extended.count("Example Learning") == 1
        assert "Software Engineer → Senior Software Engineer" in extended

    def test_extended_reuses_more_verified_engagement_evidence(
        self, freelance_editions_html
    ):
        concise = freelance_editions_html["concise"]
        extended = freelance_editions_html["extended"]
        assert "Document service boundaries and compare technical options with the team." not in concise
        assert "Document service boundaries and compare technical options with the team." in extended

    def test_analytics_overlay_reveals_a_named_standalone_position(self, real_cv_data):
        from models import CareerPresentationRule
        from transforms import CVTransformer

        reveal = CareerPresentationRule(
            match={"id": "analytics"},
            set={
                "representation": "position",
                "placement": "selected_experience",
                "identity": "named",
            },
        )
        result = CVTransformer(real_cv_data).transform(
            "freelance",
            application_rules=[reveal],
        )

        assert all(item["id"] != "analytics" for item in result["engagements"])
        revealed = next(
            item
            for item in result["selected_experience"]
            if item["id"] == "analytics"
        )
        assert revealed["company"] == "Example Analytics"
        assert revealed["title"] == "Senior Software Engineer"

    def test_non_verified_evidence_does_not_render(
        self, rendered_html, freelance_editions_html
    ):
        non_verified_claims = (
            "Reduced deployment lead time by an unconfirmed amount.",
            "Example company has an unverified funding stage.",
            "Improved customer adoption by an unconfirmed amount.",
            "Example analytics product has an unverified funding stage.",
            "Reduced import duration by an unconfirmed amount.",
        )
        outputs = {**rendered_html}
        outputs.update(
            {
                f"freelance-{edition}": html
                for edition, html in freelance_editions_html.items()
            }
        )
        for variant, html in outputs.items():
            for claim in non_verified_claims:
                assert claim not in html, f"{variant}: non-verified claim rendered"

    def test_unselected_practice_evidence_does_not_render(
        self, real_cv_data, rendered_html, freelance_editions_html
    ):
        outputs = {**rendered_html}
        outputs.update(
            {
                f"freelance-{edition}": html
                for edition, html in freelance_editions_html.items()
            }
        )
        for variant, html in outputs.items():
            for item in real_cv_data.practice_evidence.items:
                assert item.statement not in html, (
                    f"{variant}: unselected practice evidence rendered"
                )


class TestVariantProfiles:
    def test_each_variant_uses_its_own_profile(self, rendered_html):
        shared = "Senior Software Engineer"
        assert shared in rendered_html["employment"]
        assert shared in rendered_html["contracting"]
        assert "Independent Backend Consultant" in rendered_html["freelance"]


class TestCareerEvidenceInventory:
    def test_all_required_evidence_gap_categories_are_present(self, real_cv_data):
        open_categories = {
            gap.category
            for gap in real_cv_data.career_evidence.gaps
            if gap.status == "open"
        }
        assert open_categories == {
            "scale",
            "performance",
            "cost",
            "reliability",
            "delivery",
            "integration",
            "team_impact",
        }

    def test_inventory_retains_non_verified_evidence(self, real_cv_data):
        states = {item.state for item in real_cv_data.career_evidence.items}
        assert {"candidate", "verified", "rejected"} <= states


class TestSharedSections:
    def test_default_sidebar_sections_present_in_all_variants(self, rendered_html):
        for variant, html in rendered_html.items():
            for heading in ("Contact", "Skills", "Education", "Languages"):
                assert f">{heading}</h2>" in html, f"{variant} missing {heading}"
            assert ">Interests</h2>" not in html, f"{variant}: Interests rendered"

    def test_skills_use_technical_and_capabilities_subsections(self, rendered_html):
        for variant, html in rendered_html.items():
            assert ">Technical</h3>" in html, variant
            assert ">Capabilities</h3>" in html, variant
            assert ">Professional</h3>" not in html, variant

    def test_only_canonical_languages_render(self, rendered_html):
        for variant, html in rendered_html.items():
            assert "English" in html and "German" in html, variant
            assert "French" not in html and "Spanish" not in html, variant

    def test_sidebar_section_order_is_resolved(self, rendered_html):
        for variant, html in rendered_html.items():
            positions = [
                html.index(f'data-sidebar-section="{section}"')
                for section in ("contact", "skills", "education", "languages")
            ]
            assert positions == sorted(positions), variant
            assert html.count("cv-sidebar-detail-standard") == 4, variant
