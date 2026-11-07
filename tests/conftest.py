"""
Shared pytest configuration and fixtures.

Adds src/ to the import path so tests can import models/transforms the
same way the scripts do, and provides reusable sample data fixtures.
"""

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Make src/ importable (mirrors how scripts/ set up their path)
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

VARIANTS = ["employment", "contracting", "freelance"]


def _experience(
    exp_id: str,
    *,
    company: str = "Acme Corp",
    company_anonymous: str = "Series A Startup",
    employment_type: str = "full_time",
    relationship: str = "employment",
) -> Dict[str, Any]:
    """Build a single valid experience dict with sensible defaults."""
    return {
        "id": exp_id,
        "title": "Software Engineer",
        "company": company,
        "company_anonymous": company_anonymous,
        "location": "Remote",
        "start_date": "2020-01",
        "end_date": "2022-01",
        "employment_type": employment_type,
        "relationship": relationship,
        "is_current": False,
        "technologies": ["Python", "Django"],
        "summary_evidence_id": None,
        "evidence_ids": [],
    }


def _career_policy() -> Dict[str, Any]:
    """Build a minimal external career policy for model and transform tests."""
    return {
        "defaults": {
            "representation": "omitted",
            "placement": "work_history",
            "identity": "named",
            "detail": "standard",
            "order": 999,
        },
        "details": {
            "compact": {
                "max_contributions": 1,
                "max_outcomes": 1,
                "max_technologies": 1,
            },
            "standard": {
                "max_contributions": 2,
                "max_outcomes": 1,
                "max_technologies": 2,
            },
            "extended": {
                "max_contributions": None,
                "max_outcomes": None,
                "max_technologies": None,
            },
        },
        "variants": {
            "employment": {
                "rules": [
                    {
                        "match": {"has_position": True},
                        "set": {
                            "representation": "position",
                            "placement": "work_history",
                            "detail": "extended",
                            "order": 1,
                        },
                    }
                ]
            },
            "contracting": {"extends": "employment", "rules": []},
            "freelance": {
                "rules": [
                    {
                        "match": {"relationship": "freelance_contract"},
                        "set": {
                            "representation": "engagement",
                            "placement": "consultancy_engagements",
                            "identity": "anonymous",
                            "detail": "standard",
                            "order": 1,
                        },
                    }
                ]
            },
        },
        "editions": {
            "freelance_concise": {
                "variant": "freelance",
                "edition": "concise",
                "rules": [],
            },
            "freelance_extended": {
                "variant": "freelance",
                "edition": "extended",
                "rules": [
                    {
                        "match": {"relationship": "freelance_contract"},
                        "set": {"detail": "extended"},
                    }
                ],
            },
        },
    }


def _sidebar_config() -> Dict[str, Any]:
    """Build a minimal layered sidebar configuration for unit tests."""
    return {
        "inventory": {
            "technical_skill_groups": [
                {
                    "id": "skill-group.backend",
                    "state": "verified",
                    "label": "Backend",
                    "items": ["Python"],
                }
            ],
            "capabilities": [
                {
                    "id": "capability.leadership",
                    "state": "verified",
                    "label": "Technical leadership",
                }
            ],
            "languages": [
                {
                    "id": "language.english",
                    "state": "verified",
                    "name": "English",
                    "proficiency": "Native",
                }
            ],
            "interests": [
                {
                    "id": "interest.reading",
                    "state": "verified",
                    "label": "Reading",
                }
            ],
        },
        "selection": {
            "technical_skill_groups": ["skill-group.backend"],
            "capabilities": ["capability.leadership"],
            "languages": ["language.english"],
            "interests": [],
        },
        "policy": {
            "defaults": {
                "contact": {
                    "representation": "section",
                    "placement": "sidebar_primary",
                    "detail": "standard",
                    "order": 1,
                },
                "skills": {
                    "representation": "section",
                    "placement": "sidebar_primary",
                    "detail": "standard",
                    "order": 2,
                },
                "education": {
                    "representation": "section",
                    "placement": "sidebar_primary",
                    "detail": "standard",
                    "order": 3,
                },
                "languages": {
                    "representation": "section",
                    "placement": "sidebar_continuation",
                    "detail": "standard",
                    "order": 1,
                },
                "interests": {
                    "representation": "omitted",
                    "placement": "sidebar_continuation",
                    "detail": "compact",
                    "order": 2,
                },
            },
            "variants": {
                "employment": {"sections": {}},
                "contracting": {"extends": "employment", "sections": {}},
                "freelance": {
                    "sections": {
                        "languages": {
                            "placement": "sidebar_primary",
                            "order": 4,
                        }
                    }
                },
            },
            "editions": {
                "freelance_concise": {
                    "variant": "freelance",
                    "sections": {},
                },
                "freelance_extended": {
                    "variant": "freelance",
                    "sections": {
                        "languages": {
                            "placement": "sidebar_continuation",
                            "order": 1,
                        }
                    },
                },
            },
        },
    }


@pytest.fixture
def minimal_cv_dict() -> Dict[str, Any]:
    """A minimal, valid CVData-compatible dict."""
    return {
        "personal_info": {
            "first_name": "Test",
            "last_name": "User",
            "title": "Engineer",
            "photo": "assets/avatar.jpg",
        },
        "contact": {
            "phone": "+1 000",
            "email": "test@example.com",
            "location": "Remote",
            "linkedin": "linkedin.com/in/test",
        },
        "profile": {
            "employment": "Employment profile.",
            "contracting": "Contracting profile.",
            "freelance": "Freelance profile.",
        },
        "sidebar": _sidebar_config(),
        "education": [
            {
                "degree": "BSc",
                "institution": "University",
                "start_year": 2010,
                "end_year": 2014,
            }
        ],
        "career_evidence": {"items": [], "gaps": []},
        "practice_evidence": {"items": [], "gaps": []},
        "career_policy": _career_policy(),
        "consultancy": {
            "title": "Independent Consultant",
            "start_date": "2021-01",
            "end_date": "present",
        },
        "experience": [_experience("job1")],
    }


@pytest.fixture
def make_experience():
    """Expose the experience builder to tests."""
    return _experience


# --- Integration fixtures (operate on the real cv_data.yaml) ----------------


@pytest.fixture(scope="session")
def real_cv_data():
    """The actual CVData loaded + validated from data/cv_data.yaml."""
    from data_loader import load_cv_data

    return load_cv_data(PROJECT_ROOT)


@pytest.fixture(scope="session")
def rendered_html(real_cv_data):
    """Real pipeline → {variant: html} for all variants (no browser needed)."""
    from transforms import CVTransformer
    from renderer import TemplateRenderer

    transformer = CVTransformer(real_cv_data)
    renderer = TemplateRenderer(project_root=PROJECT_ROOT)
    return {v: renderer.render(v, transformer.transform(v)) for v in VARIANTS}


@pytest.fixture(scope="session")
def freelance_editions_html(real_cv_data):
    """Render both explicit freelance editions without a browser."""
    from transforms import CVTransformer
    from renderer import TemplateRenderer

    transformer = CVTransformer(real_cv_data)
    renderer = TemplateRenderer(project_root=PROJECT_ROOT)
    return {
        edition: renderer.render(
            "freelance", transformer.transform("freelance", edition=edition)
        )
        for edition in ("concise", "extended")
    }


@pytest.fixture(scope="session")
def long_employment_html(real_cv_data):
    """Synthetic employment document guaranteed to exercise page 3+."""
    from transforms import CVTransformer
    from renderer import TemplateRenderer

    data = CVTransformer(real_cv_data).transform("employment")
    data["experience"] = data["experience"] * 3
    return TemplateRenderer(project_root=PROJECT_ROOT).render("employment", data)


@pytest.fixture(scope="session")
def freelance_extended_html(real_cv_data):
    """Freelance output with the extended-edition sidebar policy applied."""
    from transforms import CVTransformer
    from renderer import TemplateRenderer

    data = CVTransformer(real_cv_data).transform("freelance", edition="extended")
    return TemplateRenderer(project_root=PROJECT_ROOT).render("freelance", data)


@pytest.fixture(scope="session")
def built_pdfs(
    rendered_html,
    long_employment_html,
    freelance_extended_html,
    tmp_path_factory,
):
    """
    Real variants plus a synthetic long document, built once per session.

    Skips the whole test if Playwright's Chromium isn't installed, so the
    suite still runs in browser-less environments.
    """
    try:
        from generator import PDFGenerator
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"playwright not available: {e}")

    out = tmp_path_factory.mktemp("pdfs")
    gen = PDFGenerator()
    paths = {}
    try:
        for variant, html in rendered_html.items():
            paths[variant] = gen.generate(html, out / f"{variant}.pdf")
        paths["employment-long"] = gen.generate(
            long_employment_html, out / "employment-long.pdf"
        )
        paths["freelance-extended"] = gen.generate(
            freelance_extended_html, out / "freelance-extended.pdf"
        )
    except Exception as e:  # Chromium missing / launch failure
        pytest.skip(f"Chromium unavailable for PDF generation: {e}")
    return paths
