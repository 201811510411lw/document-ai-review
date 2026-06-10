"""Compatibility import for the food_license workflow state.

New code should use app.workflows.food_license.state.
"""

from app.workflows.food_license.state import FoodLicenseWorkflowState


__all__ = ["FoodLicenseWorkflowState"]
