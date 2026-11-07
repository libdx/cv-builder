"""Resolve canonical CV data through audience, edition, and overlay rules."""

from typing import Any, Dict, List, Optional, Sequence

from models import (
    ApplicationCareerEvidenceSelection,
    ApplicationOverlay,
    CVData,
    CareerPresentationRule,
    EditionType,
    Experience,
    VariantType,
)


class CVTransformer:
    """Transform validated canonical data into one rendering context."""

    def __init__(self, cv_data: CVData):
        self.cv_data = cv_data

    def transform(
        self,
        variant: VariantType,
        edition: Optional[EditionType] = None,
        application_rules: Optional[Sequence[CareerPresentationRule]] = None,
        application: Optional[ApplicationOverlay] = None,
    ) -> Dict[str, Any]:
        """Resolve defaults, variant, edition, then optional overlay rules."""
        if application is not None and application_rules is not None:
            raise ValueError(
                "Pass an application overlay or application rules, not both"
            )
        if application is not None:
            if variant != application.target.variant:
                raise ValueError(
                    f"Application '{application.id}' targets variant "
                    f"'{application.target.variant}', not '{variant}'"
                )
            if edition is None:
                edition = application.target.edition
            elif edition != application.target.edition:
                raise ValueError(
                    f"Application '{application.id}' targets edition "
                    f"'{application.target.edition}', not '{edition}'"
                )

        resolved_edition = self._resolve_edition(variant, edition)
        rules = (
            application.career_presentation
            if application is not None
            else application_rules or ()
        )
        career_evidence = application.career_evidence if application is not None else ()
        career = self._transform_career(
            variant,
            resolved_edition,
            rules,
            career_evidence,
        )
        personal_info = self.cv_data.personal_info.model_dump()
        profile = self.cv_data.profile[variant]
        if application is not None:
            if application.copy_override.headline is not None:
                personal_info["title"] = application.copy_override.headline
            if application.copy_override.profile is not None:
                profile = application.copy_override.profile
        return {
            "personal_info": personal_info,
            "contact": self.cv_data.contact.model_dump(),
            "profile": profile,
            **self._transform_sidebar(variant, resolved_edition, application),
            "consultancy": self.cv_data.consultancy.model_dump(),
            "practice_evidence": self._transform_practice_evidence(application),
            "application": self._application_context(application),
            **career,
            "variant": variant,
            "edition": resolved_edition,
        }

    @staticmethod
    def _resolve_edition(
        variant: VariantType,
        edition: Optional[EditionType],
    ) -> Optional[EditionType]:
        """Default freelance to concise and reject unsupported combinations."""
        if variant == "freelance":
            if edition is None:
                return "concise"
            if edition not in {"concise", "extended"}:
                raise ValueError(
                    f"Unsupported edition '{edition}' for variant 'freelance'; "
                    "choose 'concise' or 'extended'"
                )
            return edition
        if edition is not None:
            raise ValueError(
                f"Edition '{edition}' is unsupported for variant '{variant}'; "
                "--edition is only available with freelance"
            )
        return None

    def _transform_sidebar(
        self,
        variant: VariantType,
        edition: Optional[EditionType],
        application: Optional[ApplicationOverlay],
    ) -> Dict[str, Any]:
        """Resolve canonical sidebar content through external policies."""
        config = self.cv_data.sidebar
        selection = config.selection
        inventory = config.inventory
        application_selection = (
            application.sidebar.selection if application is not None else None
        )

        def selected_ids(field_name):
            if application_selection is not None:
                application_ids = getattr(application_selection, field_name)
                if application_ids is not None:
                    return application_ids
            return getattr(selection, field_name)

        technical = self._select_inventory(
            inventory.technical_skill_groups,
            selected_ids("technical_skill_groups"),
        )
        capabilities = self._select_inventory(
            inventory.capabilities,
            selected_ids("capabilities"),
        )
        languages = self._select_inventory(
            inventory.languages,
            selected_ids("languages"),
        )
        interests = self._select_inventory(
            inventory.interests,
            selected_ids("interests"),
        )

        resolved = {
            section_id: section.model_dump()
            for section_id, section in config.policy.defaults.items()
        }

        def apply_overrides(overrides):
            for section_id, override in overrides.items():
                resolved[section_id].update(override.model_dump(exclude_none=True))

        for layer in self._variant_layers(config.policy.variants, variant):
            apply_overrides(layer.sections)

        if edition is not None:
            edition_key = f"{variant}_{edition}"
            edition_policy = config.policy.editions.get(edition_key)
            if edition_policy is None or edition_policy.variant != variant:
                raise ValueError(
                    f"Unsupported sidebar edition '{edition}' for '{variant}'"
                )
            apply_overrides(edition_policy.sections)

        if application is not None:
            apply_overrides(application.sidebar.sections)

        placement_rank = {
            "sidebar_primary": 0,
            "sidebar_continuation": 1,
        }
        sidebar = [
            {"id": section_id, **policy}
            for section_id, policy in resolved.items()
            if policy["representation"] == "section"
        ]
        sidebar.sort(
            key=lambda section: (
                placement_rank[section["placement"]],
                section["order"],
            )
        )

        return {
            "sidebar": sidebar,
            "skills": {
                "technical": [
                    {"label": item.label, "items": item.items} for item in technical
                ],
                "capabilities": [item.label for item in capabilities],
            },
            "education": [edu.model_dump() for edu in self.cv_data.education],
            "languages": [
                {"name": item.name, "proficiency": item.proficiency}
                for item in languages
            ],
            "interests": [item.label for item in interests],
        }

    @staticmethod
    def _select_inventory(items, selected_ids):
        """Return inventory objects in canonical selection order."""
        index = {item.id: item for item in items}
        selected = []
        for item_id in selected_ids:
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
            selected.append(item)
        return selected

    def _transform_practice_evidence(
        self,
        application: Optional[ApplicationOverlay],
    ) -> List[Dict[str, Any]]:
        """Resolve verified cross-career practice selected by one application."""
        if application is None:
            return []
        index = {item.id: item for item in self.cv_data.practice_evidence.items}
        selected = []
        for evidence_id in application.practice_evidence_ids:
            item = index.get(evidence_id)
            if item is None:
                raise ValueError(
                    f"Application references unknown practice evidence "
                    f"'{evidence_id}'"
                )
            if item.disclosure != "external":
                raise ValueError(
                    f"Application practice evidence '{evidence_id}' is private "
                    "and is not approved for external use"
                )
            if item.state != "verified":
                raise ValueError(
                    f"Application practice evidence '{evidence_id}' must be "
                    f"verified, not '{item.state}'"
                )
            selected.append(
                {
                    "id": item.id,
                    "kind": item.kind,
                    "statement": item.statement,
                    "tags": list(item.tags),
                }
            )
        return selected

    @staticmethod
    def _application_context(
        application: Optional[ApplicationOverlay],
    ) -> Optional[Dict[str, Any]]:
        """Expose current engagement facts for downstream application copy."""
        if application is None:
            return None
        return {
            "id": application.id,
            "output_id": application.output_id,
            "vacancy": application.vacancy.model_dump(mode="json"),
            "engagement_terms": (
                application.engagement_terms.model_dump(exclude_none=True)
                if application.engagement_terms is not None
                else {}
            ),
        }

    @staticmethod
    def _variant_layers(layers, variant):
        """Return inherited policy layers from base to most specific."""
        resolved = []
        seen = set()
        current = variant
        while current is not None:
            if current in seen:  # model validation guards this; defensive here
                raise ValueError("Variant policy inheritance cycle")
            seen.add(current)
            layer = layers[current]
            resolved.append(layer)
            current = layer.extends
        return list(reversed(resolved))

    def _transform_career(
        self,
        variant: VariantType,
        edition: Optional[EditionType],
        application_rules: Sequence[CareerPresentationRule],
        application_evidence: Sequence[ApplicationCareerEvidenceSelection],
    ) -> Dict[str, Any]:
        """Resolve career presentation and project evidence into render groups."""
        experience_ids = {experience.id for experience in self.cv_data.experience}
        unknown_overlay_ids = {
            rule.match.id
            for rule in application_rules
            if rule.match.id is not None and rule.match.id not in experience_ids
        }
        if unknown_overlay_ids:
            raise ValueError(
                "Application presentation rules reference unknown records: "
                + ", ".join(sorted(unknown_overlay_ids))
            )
        evidence_by_record = {
            selection.record_id: selection for selection in application_evidence
        }
        unknown_evidence_records = set(evidence_by_record) - experience_ids
        if unknown_evidence_records:
            raise ValueError(
                "Application career evidence references unknown records: "
                + ", ".join(sorted(unknown_evidence_records))
            )

        placements: Dict[str, List[Dict[str, Any]]] = {
            "work_history": [],
            "consultancy_engagements": [],
            "selected_experience": [],
            "prior_employment": [],
            "earlier_history": [],
        }
        diagnostics = []

        for source_index, experience in enumerate(self.cv_data.experience):
            presentation, sources = self._resolve_career_presentation(
                experience,
                variant,
                edition,
                application_rules,
            )
            diagnostics.append(
                {
                    "id": experience.id,
                    **presentation,
                    "sources": sources,
                }
            )
            if presentation["representation"] == "omitted":
                continue

            rendered = self._renderable_career_record(
                experience,
                presentation,
                evidence_by_record.get(experience.id),
            )
            rendered["_source_index"] = source_index
            placements[presentation["placement"]].append(rendered)

        for items in placements.values():
            items.sort(
                key=lambda item: (item["presentation"]["order"], item["_source_index"])
            )
            for item in items:
                del item["_source_index"]

        return {
            "experience": placements["work_history"],
            "engagements": placements["consultancy_engagements"],
            "selected_experience": placements["selected_experience"],
            "prior_employment": placements["prior_employment"],
            "earlier_history": self._group_earlier_history(
                placements["earlier_history"]
            ),
            "resolved_presentations": diagnostics,
        }

    def _resolve_career_presentation(
        self,
        experience: Experience,
        variant: VariantType,
        edition: Optional[EditionType],
        application_rules: Sequence[CareerPresentationRule],
    ) -> tuple[Dict[str, Any], Dict[str, str]]:
        """Resolve generic presentation properties with deterministic precedence."""
        policy = self.cv_data.career_policy
        resolved = policy.defaults.model_dump()
        sources = {property_name: "defaults" for property_name in resolved}

        def apply_rules(rules, source):
            for rule in rules:
                if not self._rule_matches(experience, rule):
                    continue
                for property_name, value in rule.set.model_dump(
                    exclude_none=True
                ).items():
                    resolved[property_name] = value
                    sources[property_name] = source

        for layer_variant, layer in self._named_variant_layers(
            policy.variants, variant
        ):
            apply_rules(layer.rules, f"variant:{layer_variant}")

        if edition is not None:
            edition_key = f"{variant}_{edition}"
            edition_policy = policy.editions.get(edition_key)
            if edition_policy is None:
                raise ValueError(
                    f"Unsupported career edition '{edition}' for '{variant}'"
                )
            apply_rules(edition_policy.rules, f"edition:{edition_key}")

        apply_rules(application_rules, "application_overlay")
        self._validate_resolved_presentation(experience, resolved)
        return resolved, sources

    @staticmethod
    def _named_variant_layers(layers, variant):
        """Return ``(name, layer)`` pairs from inherited base to child."""
        resolved = []
        seen = set()
        current = variant
        while current is not None:
            if current in seen:
                raise ValueError("Career variant policy inheritance cycle")
            seen.add(current)
            layer = layers[current]
            resolved.append((current, layer))
            current = layer.extends
        return list(reversed(resolved))

    @staticmethod
    def _rule_matches(
        experience: Experience,
        rule: CareerPresentationRule,
    ) -> bool:
        match = rule.match
        return all(
            (
                match.id is None or experience.id == match.id,
                match.relationship is None
                or experience.relationship == match.relationship,
                match.has_position is None
                or bool(experience.title) == match.has_position,
            )
        )

    @staticmethod
    def _validate_resolved_presentation(
        experience: Experience,
        presentation: Dict[str, Any],
    ) -> None:
        representation = presentation["representation"]
        placement = presentation["placement"]
        allowed_placements = {
            "engagement": {"consultancy_engagements"},
            "position": {
                "work_history",
                "selected_experience",
                "prior_employment",
                "earlier_history",
            },
        }
        if (
            representation != "omitted"
            and placement not in allowed_placements[representation]
        ):
            allowed = ", ".join(sorted(allowed_placements[representation]))
            raise ValueError(
                f"Career record '{experience.id}' representation "
                f"'{representation}' cannot use placement '{placement}'; "
                f"choose one of: {allowed}"
            )
        if representation == "position" and not experience.title:
            raise ValueError(
                f"Career record '{experience.id}' cannot render as a position"
            )
        if (
            representation == "engagement"
            and experience.relationship != "freelance_contract"
        ):
            raise ValueError(
                f"Career record '{experience.id}' cannot render as an engagement"
            )
        if presentation["identity"] == "anonymous" and not experience.company_anonymous:
            raise ValueError(
                f"Career record '{experience.id}' requires a safe anonymous label"
            )

    def _renderable_career_record(
        self,
        experience: Experience,
        presentation: Dict[str, Any],
        application_evidence: Optional[ApplicationCareerEvidenceSelection] = None,
    ) -> Dict[str, Any]:
        """Project one record into position or engagement copy from verified evidence."""
        evidence_index = {item.id: item for item in self.cv_data.career_evidence.items}
        detail = self.cv_data.career_policy.details[presentation["detail"]]

        summary_evidence_id = experience.summary_evidence_id
        evidence_ids = experience.evidence_ids
        if application_evidence is not None:
            if "summary_evidence_id" in application_evidence.model_fields_set:
                summary_evidence_id = application_evidence.summary_evidence_id
            if application_evidence.evidence_ids is not None:
                evidence_ids = application_evidence.evidence_ids

        if application_evidence is None:
            summary = (
                evidence_index.get(summary_evidence_id)
                if summary_evidence_id is not None
                else None
            )
        else:
            summary = (
                self._validated_application_evidence(
                    evidence_index,
                    summary_evidence_id,
                    experience.id,
                )
                if summary_evidence_id is not None
                else None
            )
        scope = []
        if detail.include_scope and summary is not None and summary.state == "verified":
            scope.append(summary.statement)

        if application_evidence is None:
            selected = [
                evidence_index[evidence_id]
                for evidence_id in evidence_ids
                if evidence_id in evidence_index
                and evidence_index[evidence_id].state == "verified"
            ]
        else:
            selected = [
                self._validated_application_evidence(
                    evidence_index,
                    evidence_id,
                    experience.id,
                )
                for evidence_id in evidence_ids
            ]
        contributions = [
            item.statement
            for item in selected
            if item.kind in {"responsibility", "contribution"}
        ]
        outcomes = [item.statement for item in selected if item.kind == "outcome"]
        contributions = self._limit(contributions, detail.max_contributions)
        outcomes = self._limit(outcomes, detail.max_outcomes)
        technologies = self._limit(
            list(experience.technologies), detail.max_technologies
        )

        identity = (
            experience.company
            if presentation["identity"] == "named"
            else experience.company_anonymous
        )
        common = {
            "id": experience.id,
            "company": identity,
            "relationship": experience.relationship,
            "technologies": technologies,
            "presentation": dict(presentation),
        }

        if presentation["representation"] == "engagement":
            return {
                **common,
                "context": identity,
                "scope": scope,
                "contributions": contributions,
                "outcomes": outcomes,
            }

        return {
            **common,
            "title": experience.title,
            "location": experience.location,
            "start_date": experience.start_date,
            "end_date": experience.end_date,
            "description": scope[0] if scope else "",
            "achievements": contributions + outcomes,
            "anonymized": presentation["identity"] == "anonymous",
        }

    @staticmethod
    def _validated_application_evidence(
        evidence_index,
        evidence_id: str,
        record_id: str,
    ):
        item = evidence_index.get(evidence_id)
        if item is None:
            raise ValueError(
                f"Application career selection references unknown evidence "
                f"'{evidence_id}'"
            )
        if item.career_record_id != record_id:
            raise ValueError(
                f"Application evidence '{evidence_id}' belongs to "
                f"'{item.career_record_id}', not '{record_id}'"
            )
        if item.state != "verified":
            raise ValueError(
                f"Application evidence '{evidence_id}' must be verified, "
                f"not '{item.state}'"
            )
        return item

    @staticmethod
    def _limit(items: List[str], limit: Optional[int]) -> List[str]:
        return items if limit is None else items[:limit]

    @staticmethod
    def _group_earlier_history(
        positions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compress older positions into one line per organization without copying facts."""
        grouped: Dict[str, Dict[str, Any]] = {}
        for position in positions:
            company = position["company"]
            group = grouped.setdefault(
                company,
                {
                    "company": company,
                    "start_date": position["start_date"],
                    "end_date": position["end_date"],
                    "positions": [],
                },
            )
            group["start_date"] = min(group["start_date"], position["start_date"])
            group["end_date"] = max(group["end_date"], position["end_date"])
            group["positions"].append(
                {
                    "title": position["title"],
                    "start_date": position["start_date"],
                }
            )

        result = []
        for group in grouped.values():
            group["positions"].sort(key=lambda item: item["start_date"])
            group["titles"] = [item["title"] for item in group.pop("positions")]
            result.append(group)
        return result


class TransformPipeline:
    """Convenience wrapper for default output of every audience variant."""

    def __init__(self, cv_data: CVData):
        self.transformer = CVTransformer(cv_data)

    def transform_all(self) -> Dict[VariantType, Dict[str, Any]]:
        variants: List[VariantType] = ["employment", "contracting", "freelance"]
        return {variant: self.transformer.transform(variant) for variant in variants}

    def transform_one(
        self,
        variant: VariantType,
        edition: Optional[EditionType] = None,
    ) -> Dict[str, Any]:
        return self.transformer.transform(variant, edition=edition)
