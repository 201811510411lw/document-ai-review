from app.skills.base import Skill
from app.skills.contract_review import contract_review_skill
from app.skills.food_license.skill import food_license_skill
from app.skills.qc_document_review import qc_document_review_skill
from app.skills.tobacco_license_consistency_review import (
    tobacco_license_consistency_review_skill,
)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, skill_name: str) -> Skill:
        return self._skills[skill_name]

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def select(self, input_context) -> Skill:
        candidates = [
            skill for skill in self._skills.values() if skill.supports(input_context)
        ]
        if not candidates:
            raise LookupError("No registered Skill supports the input context.")
        if len(candidates) == 1:
            return candidates[0]

        declared_document_type = input_context.input.declared_document_type
        exact_name_matches = [
            skill for skill in candidates if skill.name == declared_document_type
        ]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]

        candidate_names = ", ".join(skill.name for skill in candidates)
        raise ValueError(
            f"Multiple registered Skills support the input context: {candidate_names}"
        )


skill_registry = SkillRegistry()
skill_registry.register(food_license_skill)
skill_registry.register(qc_document_review_skill)
skill_registry.register(tobacco_license_consistency_review_skill)
skill_registry.register(contract_review_skill)
