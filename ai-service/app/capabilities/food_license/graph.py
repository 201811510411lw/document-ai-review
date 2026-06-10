"""Compatibility imports for the food_license workflow runtime.

New code should use app.workflows.food_license.
"""

from app.workflows.food_license.workflow import (
    build_food_license_graph,
    food_license_graph,
    run_food_license_workflow,
)


__all__ = [
    "build_food_license_graph",
    "food_license_graph",
    "run_food_license_workflow",
]
