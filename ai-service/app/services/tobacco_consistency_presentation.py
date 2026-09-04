from collections.abc import Iterable, Mapping
from typing import Any


_STANDARD_REQUIREMENT = (
    "《烟草证》+《营业执照》满足：三信息均对应一致（企业名称、负责人、经营地址均一致）。"
)
_STORE_IN_STORE_REQUIREMENT = (
    "具备2个《营业执照》+《烟草证》，其中《烟草证》+《营业执照1》满足："
    "三信息均对应一致（企业名称、负责人、经营地址均一致），《营业执照1》+"
    "《营业执照2》+《烟草证》都满足：经营地址一致或基本重合"
    "（《营业执照2》是用来经营零食有鸣的）。"
)
_CONSISTENCY_REQUIREMENT = (
    "按照法律规定，《营业执照》与《烟草证》对应的三信息（企业名称、负责人、经营地址）"
    "必须一致。"
)
_STANDARD_LEGAL_RISK = (
    "若未变更被执法机关查到，轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌"
    "造成不良影响。"
)
_STANDARD_REMEDIATION = (
    "建议：1、加盟商变更一致后经营；2、如无法变更，可能带来较大风险：包括被执法机关"
    "查到后轻则限期整改，重则被罚款、取消烟草证等后果，以及其他对我司品牌造成不良影响"
    "的风险。"
)
_ADDRESS_REMEDIATION = (
    "建议：1、加盟商变更一致后经营；2、若地址实为同一地址但有不同的叫法，需上传门店"
    "门牌号照片（照片显示一个门店能对应两个不同的门牌号），或者相关政府机构出具的证明"
    "（如当地派出所/房管局/社区委员会等出具的地址一致的证明文件）；3、如无法变更，可能"
    "带来较大风险：包括被执法机关查到后轻则限期整改，重则被罚款、取消烟草证等后果，"
    "以及其他对我司品牌造成不良影响的风险。"
)

_RULE_SUGGESTIONS = {
    "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH": (
        f"主体名称：单店：{_STANDARD_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        f"现企业名称不一致，需变更为一致，{_STANDARD_LEGAL_RISK}{_STANDARD_REMEDIATION}"
    ),
    "BUSINESS_TOBACCO_ADDRESS_MATCH": (
        f"经营地址：单店：{_STANDARD_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        "卖烟只能在烟草证上的经营地址上售卖，所以要在零食有鸣门店里卖烟，门店的经营地址"
        f"必须是烟草证上的经营地址。现经营地址不一致，需变更为一致，{_STANDARD_LEGAL_RISK}"
        f"{_ADDRESS_REMEDIATION}"
    ),
    "BUSINESS_TOBACCO_PERSON_MATCH": (
        f"法定代表人/负责人：单店：{_STANDARD_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        "现企业负责人/法定代表人不一致，需变更为一致，"
        f"{_STANDARD_LEGAL_RISK}{_STANDARD_REMEDIATION}"
    ),
    "BUSINESS_TOBACCO_TOBACCO_VALIDITY": (
        "烟草证已过期或临近过期，请前往当地烟草专卖局办理续期后重新提交。"
    ),
    "STORE_IN_STORE_HOLDER_NAME_MATCH": (
        f"主体名称：店中店：{_STORE_IN_STORE_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        f"现企业名称不一致，需变更为一致，{_STANDARD_LEGAL_RISK}{_STANDARD_REMEDIATION}"
    ),
    "STORE_IN_STORE_HOLDER_PERSON_MATCH": (
        f"法定代表人/负责人：店中店：{_STORE_IN_STORE_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        "现企业负责人/法定代表人不一致，需变更为一致，"
        f"{_STANDARD_LEGAL_RISK}{_STANDARD_REMEDIATION}"
    ),
    "STORE_IN_STORE_HOLDER_ADDRESS_MATCH": (
        f"经营地址：店中店：{_STORE_IN_STORE_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        "卖烟只能在烟草证上的经营地址上售卖，所以要在零食有鸣门店里卖烟，门店的经营地址"
        f"必须是烟草证上的经营地址。现经营地址不一致，需变更为一致，{_STANDARD_LEGAL_RISK}"
        f"{_ADDRESS_REMEDIATION}"
    ),
    "STORE_IN_STORE_FRANCHISEE_ADDRESS_MATCH": (
        f"经营地址：店中店：{_STORE_IN_STORE_REQUIREMENT}{_CONSISTENCY_REQUIREMENT}"
        "卖烟只能在烟草证上的经营地址上售卖，所以要在零食有鸣门店里卖烟，门店的经营地址"
        f"必须是烟草证上的经营地址。现经营地址不一致，需变更为一致，{_STANDARD_LEGAL_RISK}"
        f"{_ADDRESS_REMEDIATION}"
    ),
    "STANDARD_FRANCHISEE_NAME_MATCH": (
        "单店模式下，营业执照和烟草证主体必须与 OA 加盟商名称一致，"
        "请核对 OA 加盟商信息或办理证照变更后重新提交。"
    ),
    "STANDARD_FRANCHISEE_NAME_EVIDENCE": (
        "OA 未提供加盟商主体名称，无法完成单店主体绑定校验，请补充后重新审核。"
    ),
    "STANDARD_UNEXPECTED_SECOND_BUSINESS_LICENSE": (
        "单店模式检测到第二张不同主体营业执照，请确认是否应选择店中店模式后重新提交。"
    ),
    "TOBACCO_LICENSE_RPA_VERIFICATION": (
        "请核实烟草证真伪并补充有效证照后重新提交。"
    ),
    "MANUAL_REVIEW_REJECTED": "请根据人工复核意见处理后重新提交",
    "MANUAL_REVIEW_MORE_INFO_REQUIRED": "请按补件要求完善材料后重新提交",
}

_CHILD_REVIEW_SUGGESTIONS = {
    "BUSINESS_LICENSE_CHILD_REVIEW_READY": (
        "请人工核对营业执照识别结果；如证照图片模糊、缺页或非原件，"
        "请重新上传清晰、完整的营业执照原件。"
    ),
    "FRANCHISEE_BUSINESS_LICENSE_CHILD_REVIEW_READY": (
        "请人工核对加盟店营业执照识别结果；如证照图片模糊、缺页或非原件，"
        "请重新上传清晰、完整的加盟店营业执照原件。"
    ),
    "TOBACCO_LICENSE_CHILD_REVIEW_READY": (
        "请人工核对烟草证识别结果；如证照图片模糊、缺页或非原件，"
        "请重新上传清晰、完整的烟草证原件。"
    ),
}

_EVIDENCE_SUGGESTIONS = {
    "BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY": (
        "请重新上传清晰、完整的营业执照原件，确保企业名称、负责人、"
        "经营地址及对应原文清晰可见。"
    ),
    "FRANCHISEE_BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY": (
        "请重新上传清晰、完整的加盟店营业执照原件，确保企业名称、"
        "经营地址及对应原文清晰可见。"
    ),
    "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY": (
        "请重新上传清晰、完整的烟草证原件，确保企业名称、负责人、经营地址、"
        "许可证号、有效期及对应原文清晰可见。"
    ),
}

_PUBLIC_MESSAGES = {
    "BUSINESS_LICENSE_CHILD_REVIEW_READY": "营业执照识别结果暂时无法支持自动核验",
    "FRANCHISEE_BUSINESS_LICENSE_CHILD_REVIEW_READY": (
        "加盟店营业执照识别结果暂时无法支持自动核验"
    ),
    "TOBACCO_LICENSE_CHILD_REVIEW_READY": "烟草证识别结果暂时无法支持自动核验",
    "BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY": "营业执照关键字段原文证据不完整",
    "FRANCHISEE_BUSINESS_LICENSE_EVIDENCE_FOR_CONSISTENCY": (
        "加盟店营业执照关键字段原文证据不完整"
    ),
    "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY": "烟草证关键字段原文证据不完整",
}

_FIELD_LABELS = {
    "subject_name": "企业名称",
    "business_address": "经营地址",
    "legal_person": "负责人",
    "license_no": "许可证号",
    "valid_to": "有效期",
    "document_type": "证照类型",
}


def tobacco_consistency_rule_suggestion(
    rule_code: str,
    details: Mapping[str, Any] | None = None,
) -> str:
    details = details or {}
    if rule_code in _RULE_SUGGESTIONS:
        return _RULE_SUGGESTIONS[rule_code]
    if rule_code in _CHILD_REVIEW_SUGGESTIONS:
        return _CHILD_REVIEW_SUGGESTIONS[rule_code]
    if rule_code in _EVIDENCE_SUGGESTIONS:
        return _EVIDENCE_SUGGESTIONS[rule_code]
    if details.get("difference") == "expired":
        return "请提供有效期内的烟草证后重新提交。"
    field_label = _FIELD_LABELS.get(str(details.get("field") or ""))
    if field_label:
        return f"请核对证照中的{field_label}，确认信息正确、完整后重新提交。"
    if "TYPE_FOR_CONSISTENCY" in rule_code:
        return "请重新上传正确的营业执照或烟草专卖零售许可证原件。"
    return "请核对相关证照材料，确认信息正确、完整后重新提交。"


def tobacco_consistency_public_message(rule_code: str, fallback: str) -> str:
    return _PUBLIC_MESSAGES.get(rule_code, fallback)


def with_tobacco_consistency_suggestion(rule: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(rule)
    if payload.get("passed") is False:
        details = payload.get("details")
        payload["suggestion"] = tobacco_consistency_rule_suggestion(
            str(payload.get("rule_code") or ""),
            details if isinstance(details, Mapping) else {},
        )
    return payload


def tobacco_consistency_action_text(reasons: Iterable[Mapping[str, Any]]) -> str:
    actions: list[str] = []
    for reason in reasons:
        action = str(reason.get("suggestion") or reason.get("message") or "").strip()
        if action and action not in actions:
            actions.append(action)
    return "\n\n".join(actions)
