"""
Pydantic data models for CV generation system.

Validates the structure and content of CV data to ensure consistency
across all variants.
"""

import re
from datetime import date
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# Type aliases
VariantType = Literal["employment", "contracting", "freelance"]
EditionType = Literal["concise", "extended"]
EmploymentType = Literal["full_time", "contract", "freelance"]
RelationshipType = Literal["employment", "freelance_contract"]
InventoryState = Literal["candidate", "verified", "retired", "rejected"]
SidebarSectionId = Literal["contact", "skills", "education", "languages", "interests"]
SidebarRepresentation = Literal["omitted", "section"]
SidebarPlacement = Literal["sidebar_primary", "sidebar_continuation"]
DetailLevel = Literal["compact", "standard", "extended"]
EvidenceState = Literal["candidate", "verified", "retired", "rejected"]
EvidenceKind = Literal["scope", "responsibility", "contribution", "outcome"]
PracticeEvidenceKind = Literal[
    "tooling",
    "workflow",
    "integration",
    "quality",
    "adoption",
]
EvidenceGapCategory = Literal[
    "scale",
    "performance",
    "cost",
    "reliability",
    "delivery",
    "integration",
    "team_impact",
]
CareerRepresentation = Literal["omitted", "position", "engagement"]
CareerPlacement = Literal[
    "work_history",
    "consultancy_engagements",
    "selected_experience",
    "prior_employment",
    "earlier_history",
]
CareerIdentity = Literal["named", "anonymous"]


class PersonalInfo(BaseModel):
    """Personal information section."""

    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    photo: Optional[str] = Field(default=None, description="Path to profile photo")


class Contact(BaseModel):
    """Contact information."""

    phone: str
    email: str
    location: str
    linkedin: str


class TechnicalSkillGroup(BaseModel):
    """A verified, reusable group of related technical skills."""

    id: str = Field(..., min_length=1)
    state: InventoryState
    label: str = Field(..., min_length=1)
    items: List[str] = Field(..., min_length=1)


class Capability(BaseModel):
    """An evidence-backed professional function."""

    id: str = Field(..., min_length=1)
    state: InventoryState
    label: str = Field(..., min_length=1)


class Language(BaseModel):
    """Language inventory item."""

    id: str = Field(..., min_length=1)
    state: InventoryState
    name: str = Field(..., min_length=1)
    proficiency: str = Field(..., min_length=1)


class Interest(BaseModel):
    """Optional interest inventory item."""

    id: str = Field(..., min_length=1)
    state: InventoryState
    label: str = Field(..., min_length=1)


class AttributeInventory(BaseModel):
    """Comprehensive sidebar attributes, including non-canonical items."""

    technical_skill_groups: List[TechnicalSkillGroup] = Field(..., min_length=1)
    capabilities: List[Capability] = Field(..., min_length=1)
    languages: List[Language] = Field(..., min_length=1)
    interests: List[Interest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [
            item.id
            for collection in (
                self.technical_skill_groups,
                self.capabilities,
                self.languages,
                self.interests,
            )
            for item in collection
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Sidebar inventory IDs must be globally unique")
        return self


class SidebarSelection(BaseModel):
    """Current canonical sidebar selection by stable inventory ID."""

    technical_skill_groups: List[str] = Field(..., min_length=1)
    capabilities: List[str] = Field(..., min_length=1)
    languages: List[str] = Field(..., min_length=1)
    interests: List[str] = Field(default_factory=list)


class SidebarSectionPolicy(BaseModel):
    """Complete default presentation policy for one sidebar section."""

    representation: SidebarRepresentation
    placement: SidebarPlacement
    detail: DetailLevel
    order: int = Field(..., ge=1)


class SidebarSectionOverride(BaseModel):
    """Sparse policy override applied after sidebar defaults."""

    representation: Optional[SidebarRepresentation] = None
    placement: Optional[SidebarPlacement] = None
    detail: Optional[DetailLevel] = None
    order: Optional[int] = Field(default=None, ge=1)


class VariantSidebarPolicy(BaseModel):
    """Audience-specific sidebar rules with optional single inheritance."""

    extends: Optional[VariantType] = None
    sections: Dict[SidebarSectionId, SidebarSectionOverride] = Field(
        default_factory=dict
    )


class EditionSidebarPolicy(BaseModel):
    """Edition-specific rules layered after an audience variant."""

    variant: VariantType
    sections: Dict[SidebarSectionId, SidebarSectionOverride] = Field(
        default_factory=dict
    )


class SidebarPolicy(BaseModel):
    """External declarative sidebar defaults, variants, and editions."""

    defaults: Dict[SidebarSectionId, SidebarSectionPolicy]
    variants: Dict[VariantType, VariantSidebarPolicy]
    editions: Dict[str, EditionSidebarPolicy] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy_graph(self):
        required_sections = {"contact", "skills", "education", "languages", "interests"}
        if set(self.defaults) != required_sections:
            raise ValueError(
                "Sidebar defaults must define contact, skills, education, "
                "languages, and interests"
            )

        required_variants = {"employment", "contracting", "freelance"}
        if set(self.variants) != required_variants:
            raise ValueError("Sidebar policy must define all audience variants")

        for variant in self.variants:
            seen = set()
            current = variant
            while current is not None:
                if current in seen:
                    raise ValueError("Sidebar variant inheritance must be acyclic")
                seen.add(current)
                layer = self.variants.get(current)
                if layer is None:
                    raise ValueError(
                        f"Sidebar variant '{variant}' extends unknown variant "
                        f"'{current}'"
                    )
                current = layer.extends
        return self


class SidebarConfig(BaseModel):
    """Resolved input boundary for inventory, selection, and policy."""

    inventory: AttributeInventory
    selection: SidebarSelection
    policy: SidebarPolicy

    @model_validator(mode="after")
    def validate_selection_references(self):
        collections = {
            "technical_skill_groups": self.inventory.technical_skill_groups,
            "capabilities": self.inventory.capabilities,
            "languages": self.inventory.languages,
            "interests": self.inventory.interests,
        }
        for field_name, items in collections.items():
            index = {item.id: item for item in items}
            selected = getattr(self.selection, field_name)
            if len(selected) != len(set(selected)):
                raise ValueError(
                    f"Sidebar selection '{field_name}' contains duplicates"
                )
            for item_id in selected:
                if item_id not in index:
                    raise ValueError(
                        f"Sidebar selection '{field_name}' references unknown ID "
                        f"'{item_id}'"
                    )
                if index[item_id].state != "verified":
                    raise ValueError(
                        f"Sidebar selection '{item_id}' must reference verified "
                        "inventory"
                    )
        return self


class Education(BaseModel):
    """Education entry."""

    degree: str
    institution: str
    start_year: int = Field(..., ge=1900, le=2100)
    end_year: int = Field(..., ge=1900, le=2100)

    @field_validator("end_year")
    @classmethod
    def validate_years(cls, end_year: int, info) -> int:
        """Ensure end year is after start year."""
        start_year = info.data.get("start_year")
        if start_year and end_year < start_year:
            raise ValueError("end_year must be >= start_year")
        return end_year


class EvidenceProvenance(BaseModel):
    """Traceable source for a career evidence item."""

    source: str = Field(..., min_length=1)
    reference: str = Field(..., min_length=1)


class CareerEvidenceItem(BaseModel):
    """Atomic career fact or claim with explicit verification lifecycle."""

    id: str = Field(..., min_length=1)
    career_record_id: str = Field(..., min_length=1)
    kind: EvidenceKind
    state: EvidenceState
    statement: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    provenance: List[EvidenceProvenance] = Field(default_factory=list)
    verification_note: Optional[str] = None
    state_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_evidence_lifecycle(self):
        expected_prefix = f"evidence.{self.career_record_id}."
        if not self.id.startswith(expected_prefix):
            raise ValueError(
                f"Evidence ID '{self.id}' must start with '{expected_prefix}'"
            )
        if not self.provenance:
            raise ValueError(f"Evidence '{self.id}' requires provenance")
        if self.state == "verified":
            if not self.verification_note or not self.verification_note.strip():
                raise ValueError(
                    f"Verified evidence '{self.id}' requires a verification note"
                )
        if self.state in {"retired", "rejected"} and (
            not self.state_reason or not self.state_reason.strip()
        ):
            raise ValueError(
                f"{self.state.capitalize()} evidence '{self.id}' requires a reason"
            )
        return self


class CareerEvidenceGap(BaseModel):
    """A durable prompt for evidence that has not yet been supplied."""

    id: str = Field(..., min_length=1)
    career_record_id: str = Field(..., min_length=1)
    category: EvidenceGapCategory
    question: str = Field(..., min_length=1)
    status: Literal["open", "resolved"] = "open"
    resolution: Optional[str] = None

    @model_validator(mode="after")
    def validate_gap_lifecycle(self):
        expected_prefix = f"gap.{self.career_record_id}."
        if not self.id.startswith(expected_prefix):
            raise ValueError(f"Gap ID '{self.id}' must start with '{expected_prefix}'")
        if self.status == "resolved" and (
            not self.resolution or not self.resolution.strip()
        ):
            raise ValueError(f"Resolved gap '{self.id}' requires a resolution")
        return self


class CareerEvidenceInventory(BaseModel):
    """Durable career evidence, including non-renderable claims and gaps."""

    items: List[CareerEvidenceItem] = Field(default_factory=list)
    gaps: List[CareerEvidenceGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [item.id for item in self.items] + [gap.id for gap in self.gaps]
        if len(ids) != len(set(ids)):
            raise ValueError("Career evidence and gap IDs must be globally unique")
        return self


class PracticeEvidenceItem(BaseModel):
    """Reusable professional practice not tied to one career record."""

    id: str = Field(..., min_length=1)
    kind: PracticeEvidenceKind
    state: EvidenceState
    # Existing public inventory retains its behavior; private facts cannot render.
    disclosure: Literal["external", "private"] = "external"
    statement: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    provenance: List[EvidenceProvenance] = Field(default_factory=list)
    verification_note: Optional[str] = None
    state_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_evidence_lifecycle(self):
        if not self.id.startswith("practice."):
            raise ValueError(
                f"Practice evidence ID '{self.id}' must start with 'practice.'"
            )
        if not self.provenance:
            raise ValueError(f"Practice evidence '{self.id}' requires provenance")
        if self.state == "verified" and (
            not self.verification_note or not self.verification_note.strip()
        ):
            raise ValueError(
                f"Verified practice evidence '{self.id}' requires a verification note"
            )
        if self.state in {"retired", "rejected"} and (
            not self.state_reason or not self.state_reason.strip()
        ):
            raise ValueError(
                f"{self.state.capitalize()} practice evidence '{self.id}' requires a reason"
            )
        return self


class PracticeEvidenceGap(BaseModel):
    """Role-driven question for a reusable professional practice."""

    id: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    status: Literal["open", "resolved"] = "open"
    resolution: Optional[str] = None

    @model_validator(mode="after")
    def validate_gap_lifecycle(self):
        if not self.id.startswith("practice-gap."):
            raise ValueError(
                f"Practice evidence gap ID '{self.id}' must start with 'practice-gap.'"
            )
        if self.status == "resolved" and (
            not self.resolution or not self.resolution.strip()
        ):
            raise ValueError(
                f"Resolved practice evidence gap '{self.id}' requires a resolution"
            )
        return self


class PracticeEvidenceInventory(BaseModel):
    """Reusable cross-career practices and unresolved practice questions."""

    items: List[PracticeEvidenceItem] = Field(default_factory=list)
    gaps: List[PracticeEvidenceGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        ids = [item.id for item in self.items] + [gap.id for gap in self.gaps]
        if len(ids) != len(set(ids)):
            raise ValueError("Practice evidence and gap IDs must be globally unique")
        return self


class ApplicationVacancy(BaseModel):
    """Source identity for one vacancy snapshot."""

    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    captured_at: date


class ApplicationTarget(BaseModel):
    """Audience and content depth selected by an application overlay."""

    variant: VariantType
    edition: Optional[EditionType] = None

    @model_validator(mode="after")
    def validate_variant_edition(self):
        if self.variant == "freelance" and self.edition is None:
            raise ValueError("Freelance application target requires an edition")
        if self.variant != "freelance" and self.edition is not None:
            raise ValueError(
                f"Application edition is unsupported for variant '{self.variant}'"
            )
        return self


class ApplicationCopyOverride(BaseModel):
    """Sparse role-specific identity and profile copy."""

    headline: Optional[str] = Field(default=None, min_length=1)
    profile: Optional[str] = Field(default=None, min_length=1)


class ApplicationSidebarSelection(BaseModel):
    """Sparse replacement lists for canonical sidebar selections."""

    technical_skill_groups: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    interests: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_unique_ids(self):
        for field_name in (
            "technical_skill_groups",
            "capabilities",
            "languages",
            "interests",
        ):
            selected = getattr(self, field_name)
            if selected is not None and len(selected) != len(set(selected)):
                raise ValueError(
                    f"Application sidebar selection '{field_name}' "
                    "contains duplicates"
                )
        return self


class ApplicationSidebarOverride(BaseModel):
    """Role-specific sidebar content and presentation changes."""

    selection: ApplicationSidebarSelection = Field(
        default_factory=ApplicationSidebarSelection
    )
    sections: Dict[SidebarSectionId, SidebarSectionOverride] = Field(
        default_factory=dict
    )


class ApplicationCareerEvidenceSelection(BaseModel):
    """Role-specific evidence order for one career record."""

    record_id: str = Field(..., min_length=1)
    summary_evidence_id: Optional[str] = None
    evidence_ids: Optional[List[str]] = None

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if self.evidence_ids is not None and len(self.evidence_ids) != len(
            set(self.evidence_ids)
        ):
            raise ValueError(
                f"Application career selection '{self.record_id}' contains "
                "duplicate evidence IDs"
            )
        return self


class ApplicationEngagementTerms(BaseModel):
    """Current application facts kept outside historical career evidence."""

    capacity: Optional[str] = Field(default=None, min_length=1)
    meeting_overlap: Optional[str] = Field(default=None, min_length=1)
    start_timing: Optional[str] = Field(default=None, min_length=1)
    commercial_terms: Optional[str] = Field(default=None, min_length=1)


class Consultancy(BaseModel):
    """Canonical identity of the independent consulting practice."""

    title: str = Field(..., min_length=1)
    start_date: str = Field(..., description="Format: YYYY-MM")
    end_date: str = Field(..., description="Format: YYYY-MM or 'present'")


class CareerRuleMatch(BaseModel):
    """Generic factual selectors for an external presentation rule."""

    id: Optional[str] = None
    relationship: Optional[RelationshipType] = None
    has_position: Optional[bool] = None

    @model_validator(mode="after")
    def validate_non_empty_match(self):
        if all(
            value is None for value in (self.id, self.relationship, self.has_position)
        ):
            raise ValueError("Career presentation rule match cannot be empty")
        return self


class CareerPresentation(BaseModel):
    """Complete generic presentation state before contextual rules."""

    representation: CareerRepresentation
    placement: CareerPlacement
    identity: CareerIdentity
    detail: DetailLevel
    order: int = Field(..., ge=1)


class CareerPresentationOverride(BaseModel):
    """Sparse changes applied by a variant, edition, or application rule."""

    representation: Optional[CareerRepresentation] = None
    placement: Optional[CareerPlacement] = None
    identity: Optional[CareerIdentity] = None
    detail: Optional[DetailLevel] = None
    order: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_non_empty_override(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("Career presentation rule override cannot be empty")
        return self


class CareerPresentationRule(BaseModel):
    """One ordered rule over factual career-record properties."""

    match: CareerRuleMatch
    set: CareerPresentationOverride


class ApplicationOverlay(BaseModel):
    """Sparse, validated tailoring instructions for one vacancy."""

    schema_version: Literal[1] = 1
    id: str = Field(..., min_length=1)
    output_id: str = Field(..., min_length=1)
    vacancy: ApplicationVacancy
    target: ApplicationTarget
    copy_override: ApplicationCopyOverride = Field(
        default_factory=ApplicationCopyOverride,
        alias="copy",
    )
    sidebar: ApplicationSidebarOverride = Field(
        default_factory=ApplicationSidebarOverride
    )
    career_presentation: List[CareerPresentationRule] = Field(default_factory=list)
    career_evidence: List[ApplicationCareerEvidenceSelection] = Field(
        default_factory=list
    )
    practice_evidence_ids: List[str] = Field(default_factory=list)
    engagement_terms: Optional[ApplicationEngagementTerms] = None

    @field_validator("id", "output_id")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError(
                "Application ID and output ID must use lowercase kebab-case"
            )
        return value

    @model_validator(mode="after")
    def validate_unique_selections(self):
        record_ids = [selection.record_id for selection in self.career_evidence]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError(
                "Application career evidence may select each record only once"
            )
        if len(self.practice_evidence_ids) != len(set(self.practice_evidence_ids)):
            raise ValueError("Application practice evidence contains duplicates")
        return self


class VariantCareerPolicy(BaseModel):
    """Audience-specific career rules with optional single inheritance."""

    extends: Optional[VariantType] = None
    rules: List[CareerPresentationRule] = Field(default_factory=list)


class EditionCareerPolicy(BaseModel):
    """Edition rules layered after one audience variant."""

    variant: VariantType
    edition: EditionType
    rules: List[CareerPresentationRule] = Field(default_factory=list)


class CareerDetailPolicy(BaseModel):
    """Reusable evidence-depth limits selected by generic detail level."""

    include_scope: bool = True
    max_contributions: Optional[int] = Field(default=None, ge=0)
    max_outcomes: Optional[int] = Field(default=None, ge=0)
    max_technologies: Optional[int] = Field(default=None, ge=0)


class CareerPolicy(BaseModel):
    """External defaults, variant rules, and edition rules for career records."""

    defaults: CareerPresentation
    details: Dict[DetailLevel, CareerDetailPolicy]
    variants: Dict[VariantType, VariantCareerPolicy]
    editions: Dict[str, EditionCareerPolicy] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_policy_graph(self):
        required_details = {"compact", "standard", "extended"}
        if set(self.details) != required_details:
            raise ValueError(
                "Career detail policy must define compact, standard, and extended"
            )

        required_variants = {"employment", "contracting", "freelance"}
        if set(self.variants) != required_variants:
            raise ValueError("Career policy must define all audience variants")

        for variant in self.variants:
            seen = set()
            current = variant
            while current is not None:
                if current in seen:
                    raise ValueError("Career variant inheritance must be acyclic")
                seen.add(current)
                layer = self.variants.get(current)
                if layer is None:
                    raise ValueError(
                        f"Career variant '{variant}' extends unknown variant "
                        f"'{current}'"
                    )
                current = layer.extends

        for key, policy in self.editions.items():
            expected_key = f"{policy.variant}_{policy.edition}"
            if key != expected_key:
                raise ValueError(
                    f"Career edition key '{key}' must match '{expected_key}'"
                )
        return self


class Experience(BaseModel):
    """Work experience entry with transformation metadata."""

    id: str = Field(..., description="Unique identifier for this experience")
    title: str
    company: str
    company_anonymous: Optional[str] = Field(
        default=None, description="Anonymized company name for freelance variant"
    )
    company_size: Optional[str] = None
    industry: Optional[str] = None
    location: str
    start_date: str = Field(..., description="Format: YYYY-MM")
    end_date: str = Field(..., description="Format: YYYY-MM or 'present'")
    employment_type: EmploymentType
    relationship: RelationshipType
    is_current: bool = False

    # Content references. Rendering text lives in the durable evidence inventory.
    technologies: List[str] = Field(default_factory=list)
    summary_evidence_id: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)


class CVData(BaseModel):
    """Complete CV data model."""

    personal_info: PersonalInfo
    contact: Contact
    profile: Dict[VariantType, str] = Field(
        ..., description="Variant-specific profile summaries"
    )
    sidebar: SidebarConfig
    education: List[Education]
    career_evidence: CareerEvidenceInventory
    practice_evidence: PracticeEvidenceInventory
    career_policy: CareerPolicy
    consultancy: Consultancy
    experience: List[Experience]

    @field_validator("profile")
    @classmethod
    def validate_profiles(cls, v: Dict[VariantType, str]) -> Dict[VariantType, str]:
        """Ensure all three variant profiles are provided."""
        required_variants: List[VariantType] = [
            "employment",
            "contracting",
            "freelance",
        ]
        for variant in required_variants:
            if variant not in v:
                raise ValueError(f"Profile text missing for variant: {variant}")
            if not v[variant].strip():
                raise ValueError(f"Profile text empty for variant: {variant}")
        return v

    @field_validator("experience")
    @classmethod
    def validate_experience_ids(cls, v: List[Experience]) -> List[Experience]:
        """Ensure all experience IDs are unique."""
        ids = [exp.id for exp in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Experience IDs must be unique")
        return v

    @model_validator(mode="after")
    def validate_canonical_evidence_selection(self):
        """Canonical experience may reference only matching verified evidence."""
        experience_ids = {experience.id for experience in self.experience}
        evidence_index = {item.id: item for item in self.career_evidence.items}

        policy_rules = [
            rule
            for layer in self.career_policy.variants.values()
            for rule in layer.rules
        ] + [
            rule
            for layer in self.career_policy.editions.values()
            for rule in layer.rules
        ]
        for rule in policy_rules:
            record_id = rule.match.id
            if record_id is not None and record_id not in experience_ids:
                raise ValueError(
                    f"Career presentation rule references unknown record "
                    f"'{record_id}'"
                )

        for item in self.career_evidence.items:
            if item.career_record_id not in experience_ids:
                raise ValueError(
                    f"Evidence '{item.id}' references unknown career record "
                    f"'{item.career_record_id}'"
                )
        for gap in self.career_evidence.gaps:
            if gap.career_record_id not in experience_ids:
                raise ValueError(
                    f"Evidence gap '{gap.id}' references unknown career record "
                    f"'{gap.career_record_id}'"
                )

        for experience in self.experience:
            selected = list(experience.evidence_ids)
            if experience.summary_evidence_id is not None:
                selected.append(experience.summary_evidence_id)
            if len(selected) != len(set(selected)):
                raise ValueError(
                    f"Career record '{experience.id}' contains duplicate evidence IDs"
                )
            for evidence_id in selected:
                item = evidence_index.get(evidence_id)
                if item is None:
                    raise ValueError(
                        f"Career record '{experience.id}' references unknown evidence "
                        f"'{evidence_id}'"
                    )
                if item.career_record_id != experience.id:
                    raise ValueError(
                        f"Evidence '{evidence_id}' belongs to '{item.career_record_id}', "
                        f"not '{experience.id}'"
                    )
                if item.state != "verified":
                    raise ValueError(
                        f"Canonical evidence '{evidence_id}' must be verified, "
                        f"not '{item.state}'"
                    )
        return self
