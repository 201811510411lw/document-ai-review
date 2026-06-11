"""
企业微信证照机器人 — 批量导入

支持从 OSS URL 列表批量导入证照数据
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional
from . import database, recognizer

logger = logging.getLogger(__name__)


def import_from_urls(
    urls: list[str],
    batch_no: Optional[str] = None,
    prompt: str = "请识别图片中的内容，提取：1.证照类型（营业执照/食品经营许可证/食品生产许可证等）2.公司名称 3.统一社会信用代码 4.有效截止日期（长期则输出2099-01-01）5.法定代表人 6.住所",
) -> dict:
    """
    从 OSS URL 列表批量导入证照

    对每个 URL:
      1. 用 Mimo V2.5 识别内容
      2. 解析为结构化字段
      3. 存入 certification_records 表

    参数:
        urls    — OSS 文件 URL 列表
        batch_no — 批次号（自动生成）
        prompt  — 识别提示词

    返回:
        {
            "batch_no": "B20260610-001",
            "total": 5,
            "success": 4,
            "fail": 1,
            "failures": [
                {"url": "...", "error": "原因"},
            ],
            "records": [
                {"id": 1, "company_name": "xxx"},
            ],
        }
    """
    if not urls:
        return {"batch_no": "", "total": 0, "success": 0, "fail": 0, "failures": [], "records": []}

    # 生成批次号
    batch_no = batch_no or f"B{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    batch_id = database.create_import_batch(batch_no)

    total = len(urls)
    success = 0
    fail = 0
    failures = []
    records = []

    print(f"[import] 开始批量导入: {batch_no} ({total} 个文件)")

    for i, url in enumerate(urls):
        file_name = url.split("/")[-1] if "/" in url else f"file_{i}"
        print(f"  [{i+1}/{total}] 识别中: {file_name}")

        try:
            # 1. 用 Mimo 识别
            raw_text = recognizer.parse_with_multimodal(url, prompt)
            if not raw_text or raw_text.strip() == "":
                raise ValueError("识别结果为空")

            print(f"    [OK] 识别成功 ({len(raw_text)} 字符)")

            # 2. 解析为结构化字段
            parsed = recognizer.parse_recognized_text(raw_text)

            # 3. 提取字段值
            company_name = (
                parsed.get("公司名称")
                or parsed.get("生产者名称")
                or parsed.get("经营者名称")
                or f"未知公司_{batch_no}_{i}"
            )
            license_type = parsed.get("证照类型", "")
            credit_code = parsed.get("统一社会信用代码", "")
            expire_date = (
                parsed.get("有效截止日期")
                or parsed.get("有效期截止日期")
                or parsed.get("营业期限截止日期")
                or parsed.get("证件到效日期")
                or ""
            )
            legal_person = parsed.get("法定代表人", "")
            address = parsed.get("住所", "")

            # 4. 存入数据库
            record_id = database.save_record(
                company_name=company_name,
                license_type=license_type,
                credit_code=credit_code,
                expire_date=expire_date,
                legal_person=legal_person,
                address=address,
                raw_text=raw_text,
                source_url=url,
                source_name=file_name,
            )

            records.append({"id": record_id, "company_name": company_name, "url": url})
            success += 1
            print(f"    [OK] 已入库: {company_name} (ID={record_id})")

        except Exception as e:
            fail += 1
            failures.append({"url": url, "error": str(e)})
            print(f"    [FAIL] 导入失败: {e}")

    # 更新批次统计
    database.update_import_batch(batch_id, success, fail)

    print(f"[import] 导入完成: 成功 {success}/{total}, 失败 {fail}")

    return {
        "batch_no": batch_no,
        "total": total,
        "success": success,
        "fail": fail,
        "failures": failures,
        "records": records,
    }


def import_from_json(json_path: str, prompt: str = None) -> dict:
    """
    从 JSON 文件导入 URL 列表

    JSON 格式:
        {"urls": ["https://oss.../img1.jpg", "https://oss.../img2.jpg"]}
    或:
        [{"url": "https://oss.../img1.jpg"}, ...]
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
    elif isinstance(data, list):
        urls = [item["url"] if isinstance(item, dict) else item for item in data]
    else:
        raise ValueError(f"无法解析 JSON 格式: {json_path}")

    return import_from_urls(urls, prompt=prompt)
