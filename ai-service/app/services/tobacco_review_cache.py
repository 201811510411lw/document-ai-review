from copy import deepcopy
from typing import Any


_reports: dict[str, dict[str, Any]] = {}


def save_tobacco_report(report: dict[str, Any]) -> None:
    _reports[str(report["id"])] = deepcopy(report)


def get_tobacco_report(task_id: str) -> dict[str, Any] | None:
    report = _reports.get(task_id)
    return deepcopy(report) if report is not None else None


def list_tobacco_reports() -> list[dict[str, Any]]:
    return [deepcopy(report) for report in reversed(list(_reports.values()))]


def apply_manual_review(task_id: str, decision: str, comment: str) -> dict[str, Any] | None:
    report = _reports.get(task_id)
    if report is None:
        return None
    result = "通过" if decision == "APPROVE" else ("不通过" if decision == "REJECT" else "待校验")
    report["overall_result"] = result
    report["manual_review"] = {"decision": decision, "comment": comment}
    return deepcopy(report)
