from app.skills.base import Skill
from app.skills.food_license.skill import food_license_skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, skill_name: str) -> Skill:
        return self._skills[skill_name]

    def list(self) -> list[Skill]:
        return list(self._skills.values())


skill_registry = SkillRegistry()
skill_registry.register(food_license_skill)
