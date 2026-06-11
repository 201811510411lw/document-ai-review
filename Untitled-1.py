"""
Mimo + Tesseract — 从 API 获取 PDF/图片并提取内容 + 数据库校验

安装依赖 (在终端执行):
  pip install langchain langchain-community pypdf requests
  pip install pdf2image pillow pytesseract   # 图片/扫描件 OCR
  pip install openai                         # Mimo 多模态识别
  pip install pymysql                        # MySQL 数据库校验（上线用）

使用前设置:
  方式 A: 编辑下方 MIMO_API_KEY 常量（开发用，不要提交到 git）
  方式 B: set MIMO_API_KEY=sk-你的key         （环境变量，推荐上线用）

数据库校验:
  test_mode=True  — 使用内置 SQLite 测试数据，无需数据库即可测试校验逻辑
  test_mode=False — 连接真实 MySQL，需先配置 MYSQL_CONFIG

Mimo API 文档: https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call
"""

import sys
import io
# 解决 Windows GBK 终端打印中文报错的问题（仅在直接运行时生效）
if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import tempfile
import os

# ============================================================
# API Key 配置
# 开发阶段：直接填 key 测试
# 上线前：清空值，改用环境变量
# ============================================================
DEEPSEEK_API_KEY = ""  # （旧，保留参考）

MIMO_API_KEY = ""  # 开发时填入，上线前清空

# ============================================================
# MySQL 数据库连接配置（校验用）
# 开发阶段：留空，test_mode=True 使用内置 SQLite 测试数据
# 上线前：填入远程 MySQL 连接信息
# ============================================================
MYSQL_CONFIG = {
    "host": "",        # 远程主机地址（上线前填写）
    "port": 3306,      # 端口号
    "user": "",        # 用户名
    "password": "",    # 密码
    "database": "",    # 数据库名
}

# ============================================================
# 字段映射配置（识别字段 → 数据库列名）
# 调用 validate_with_db() 时可通过 mapping 参数自定义覆盖
# ============================================================
FIELD_MAPPING = {
    "证照类型": "license_type",
    "公司名称": "company_name",
    "统一社会信用代码": "credit_code",
    "证件到效日期": "expire_date",
    "法定代表人": "legal_person",
    "住所": "address",
    "经营者名称": "company_name",       # 食品经营许可证上的字段
    "生产者名称": "company_name",       # 食品生产许可证上的字段
    "营业期限截止日期": "expire_date",   # 营业执照上的字段
    "有效期截止日期": "expire_date",     # 许可证上的字段
    "有效截止日期": "expire_date",       # 结构化提取的字段
}


# ============================================================
# 1. 解析 PDF（文本型）
# ============================================================
def parse_pdf_from_url(pdf_url: str) -> list[str]:
    """
    从 URL 下载 PDF 并用 PyPDF 解析文本内容
    返回每页文本列表
    """
    from langchain_community.document_loaders import PyPDFLoader

    print(f"正在下载 PDF: {pdf_url}")
    resp = requests.get(pdf_url, timeout=30)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(resp.content)
        tmp = f.name

    try:
        docs = PyPDFLoader(tmp).load()
        # docs 是一个 Document 列表，每个 Document 对应一页
        pages = [doc.page_content for doc in docs]
        print(f"解析完成，共 {len(pages)} 页")
        return pages
    finally:
        os.unlink(tmp)


# ============================================================
# 2. 解析图片（OCR 方式 — 提取图片中的文字）
# ============================================================
def parse_image_ocr(image_url: str, lang: str = "chi_sim+eng") -> str:
    """
    用 Tesseract OCR 提取图片文字
    Tesseract 下载: https://github.com/UB-Mannheim/tesseract/wiki
    安装后设置环境变量: set TESSDATA_PREFIX=C:\\Program Files\\Tesseract-OCR\\tessdata
    """
    from PIL import Image
    import pytesseract
    # 指定 tesseract 可执行文件路径（解决 PATH 找不到的问题）
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # 指定中文语言包路径（解决 TESSDATA_PREFIX 环境变量没设置的问题）
    os.environ["TESSDATA_PREFIX"] = os.path.join(os.path.expanduser("~"), "tessdata")

    resp = requests.get(image_url, timeout=30)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(resp.content)
        tmp = f.name

    try:
        from PIL import ImageFilter, ImageEnhance
        img = Image.open(tmp)
        # ----- 图片预处理：大幅减少背景噪音 -----
        # 1. 转灰度
        img = img.convert("L")
        # 2. 增强对比度（让文字更清晰）
        img = ImageEnhance.Contrast(img).enhance(2.0)
        # 3. 二值化（去底纹/水印）
        img = img.point(lambda x: 0 if x < 128 else 255)
        # 4. 轻微降噪
        img = img.filter(ImageFilter.MedianFilter(size=3))
        # ------------------------------------
        text = pytesseract.image_to_string(img, lang=lang)
        return text
    finally:
        os.unlink(tmp)


# ============================================================
# 3. 解析图片/PDF（多模态 LLM 方式 — 直接读懂内容）
# ============================================================
def parse_with_multimodal(
    file_url: str,
    prompt: str = "请提取这张图片/文档中的所有文字信息",
    api_key: str | None = None,
) -> str:
    """
    用 Mimo V2.5 多模态模型直接理解图片内容
    适合：图表、手写、扫描件、UI 截图等（需设置 MIMO_API_KEY 环境变量）

    文档: https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key or MIMO_API_KEY or os.getenv("MIMO_API_KEY"),
        base_url="https://api.xiaomimimo.com/v1",
    )

    # Mimo 兼容 OpenAI 标准格式: image_url 在 content 数组中
    resp = client.chat.completions.create(
        model="mimo-v2.5",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": file_url}},
                ],
            }
        ],
        temperature=0,
    )
    return resp.choices[0].message.content


# ============================================================
# 4. 扫描版 PDF（每页转图片 → 多模态 LLM 识别）
# ============================================================
def parse_scanned_pdf(
    pdf_url: str,
    api_key: str | None = None,
) -> str:
    """
    把 PDF 每页转成图片，逐页用 Mimo V2.5 多模态识别
    适用：扫描件、图片式 PDF（文字不可直接选取）（需设置 MIMO_API_KEY 环境变量）

    文档: https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call
    """
    from pdf2image import convert_from_bytes
    from openai import OpenAI
    import base64
    from io import BytesIO

    print(f"正在下载 PDF: {pdf_url}")
    resp = requests.get(pdf_url, timeout=30)
    resp.raise_for_status()

    print("正在将 PDF 转换为图片...")
    images = convert_from_bytes(resp.content, dpi=200)

    client = OpenAI(
        api_key=api_key or MIMO_API_KEY or os.getenv("MIMO_API_KEY"),
        base_url="https://api.xiaomimimo.com/v1",
    )

    results = []
    for i, img in enumerate(images):
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Mimo 兼容 OpenAI 标准格式
        resp = client.chat.completions.create(
            model="mimo-v2.5",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请提取第 {i+1} 页中的所有文字"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content
        results.append(f"--- 第 {i+1} 页 ---\n{text}")
        print(f"  第 {i+1}/{len(images)} 页完成")

    return "\n\n".join(results)


# ============================================================
# 5. 数据库校验
# ============================================================

def parse_recognized_text(text: str) -> dict[str, str]:
    """
    将 Mimo 多模态返回的文本解析为 {字段名: 值} 字典

    支持格式:
        "1. 证照类型：营业执照"
        "证照类型: 营业执照"
        "识别公司名称：xxx公司"

    返回:
        {"证照类型": "营业执照", "公司名称": "xxx公司", ...}
    """
    import re
    result = {}

    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # 去掉行首的 "数字. " 或 "- " 编号前缀
        line_clean = re.sub(r'^[\d\-]+[\.\、\s]*\s*', '', line)

        # 用冒号分割（支持中英文冒号）
        sep = '：' if '：' in line_clean else (':' if ':' in line_clean else None)
        if sep is None:
            continue

        parts = line_clean.split(sep, 1)
        key = parts[0].strip()
        value = parts[1].strip() if len(parts) > 1 else ""

        # 去掉 key 中的 "识别" 前缀（如 "识别公司名称" → "公司名称"）
        key = re.sub(r'^识别', '', key).strip()
        # 去掉 markdown 格式标记（**加粗**、*斜体*）
        key = key.strip('*_').strip()
        value = value.strip('*_').strip()

        if key and value:
            result[key] = value

    return result


def _init_test_db():
    """
    创建内存 SQLite 测试数据库，插入示例数据
    返回数据库连接对象
    """
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    cursor = db.cursor()

    # 创建测试表
    cursor.execute("""
        CREATE TABLE certification_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            license_type TEXT,
            credit_code TEXT,
            expire_date TEXT,
            legal_person TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 插入示例数据（模拟证照信息）
    test_data = [
        ("贵州益佰制药股份有限公司", "食品生产许可证", "91520000214304865U", "2027-11-30", "窦啟玲", "贵州省贵阳市白云大道220-1号"),
        ("北京华联综合超市股份有限公司", "食品经营许可证", "91110000802663175J", "2028-06-15", "陈琳", "北京市西城区阜外大街1号"),
        ("深圳华为技术有限公司", "营业执照", "91440300279583516U", "2099-01-01", "赵明路", "深圳市龙岗区坂田华为总部办公楼"),
    ]

    cursor.executemany(
        "INSERT INTO certification_test (company_name, license_type, credit_code, expire_date, legal_person, address) VALUES (?, ?, ?, ?, ?, ?)",
        test_data,
    )
    db.commit()

    print(f"✅ 测试数据库已初始化，包含 {len(test_data)} 条记录")
    return db


def validate_with_db(
    recognized_text: str,
    table_name: str = "certification_test",
    mapping: dict | None = None,
    test_mode: bool = True,
    db_config: dict | None = None,
) -> dict:
    """
    将多模态识别结果与数据库记录做校验

    参数:
        recognized_text — parse_with_multimodal() 等识别函数返回的文本
        table_name     — 要查询的数据库表名（test_mode=True 时无效）
        mapping        — 字段映射 {识别字段: 数据库列名}，默认使用 FIELD_MAPPING
        test_mode      — True: 使用内置 SQLite 测试数据，False: 连接真实 MySQL
        db_config      — MySQL 连接配置，默认使用 MYSQL_CONFIG 常量

    返回:
        {
            "is_match": True/False,      # 所有字段是否完全匹配
            "matched_count": 3,          # 匹配的字段数
            "total_count": 5,            # 总比对的字段数
            "match_ratio": 0.6,          # 匹配率
            "db_record_found": True,     # 是否在数据库中找到对应记录
            "details": [                 # 每个字段的比对详情
                {
                    "field": "证照类型",
                    "db_column": "license_type",
                    "recognized": "营业执照",
                    "expected": "食品经营许可证",
                    "match": False,
                },
                ...
            ],
            "expire_check": None | {    # 证照效期状态
                "expire_date_str": "2027-11-30",
                "status": "未过期",       # "未过期"|"三十天内即将过期"|"已过期"|"未知"
                "days_remaining": 567,    # 正数=剩余，负数=已过期
                "is_expired": False,
                "is_about_to_expire": False,
            },
        }

    异常:
        ConnectionError — test_mode=False 时 MySQL 连接失败或配置为空
        ValueError      — 表不存在或字段映射中的列名在表中找不到
    """
    # ----- 1. 解析识别文本为结构化的字段:值 -----
    parsed = parse_recognized_text(recognized_text)
    if not parsed:
        print("⚠️  未能从识别结果中解析出结构化字段")
        return {
            "is_match": False,
            "matched_count": 0,
            "total_count": 0,
            "match_ratio": 0.0,
            "db_record_found": False,
            "error": "未能从识别结果中解析出结构化字段",
            "details": [],
        }

    print(f"📋 解析到 {len(parsed)} 个字段: {list(parsed.keys())}")

    # ----- 2. 确定映射关系 -----
    field_map = mapping or FIELD_MAPPING

    # ----- 3. 连接数据库（测试模式 or 真实 MySQL）-----
    if test_mode:
        print("🔧 测试模式：使用内置 SQLite 测试数据")
        db = _init_test_db()
        try:
            return _do_validate(db, parsed, field_map, table_name)
        finally:
            db.close()
    else:
        cfg = db_config or MYSQL_CONFIG
        if not cfg["host"] or not cfg["database"]:
            raise ConnectionError(
                "MySQL 连接信息不完整，请先在 MYSQL_CONFIG 中配置 host 和 database"
            )
        try:
            import pymysql

            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg.get("port", 3306),
                user=cfg.get("user", ""),
                password=cfg.get("password", ""),
                database=cfg["database"],
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
            )
            print(f"✅ 已连接到 MySQL: {cfg['host']}:{cfg['port']}/{cfg['database']}")
            try:
                return _do_validate(conn, parsed, field_map, table_name)
            finally:
                conn.close()
        except ImportError:
            raise ImportError("请先安装 pymysql: pip install pymysql")



def check_expire_date(expire_date_str: str) -> dict:
    """
    检查证照到期状态

    规则:
      - 有效期 ≤ 今天 → "已过期"
      - 有效期 - 今天 > 30天 → "未过期"
      - 有效期 - 今天 ≤ 30天 → "三十天内即将过期"

    参数:
        expire_date_str — 识别出的到期日期，如 "2027-11-30"、"2099-01-01"、"长期"

    返回:
        {
            "expire_date_str": "2027-11-30",
            "status": "未过期" | "三十天内即将过期" | "已过期" | "未知",
            "days_remaining": 567,    # 正数=剩余天数，负数=已过期天数
            "is_expired": False,
            "is_about_to_expire": False,
        }
    """
    from datetime import datetime, date

    expire_str = expire_date_str.strip()

    # 处理长期有效的情况
    if expire_str in ("长期", "永久", "长期有效", "无固定期限", "2099-01-01"):
        return {
            "expire_date_str": expire_str,
            "status": "未过期",
            "days_remaining": 99999,
            "is_expired": False,
            "is_about_to_expire": False,
        }

    # 解析日期
    try:
        expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
    except ValueError:
        return {
            "expire_date_str": expire_str,
            "status": "未知",
            "days_remaining": None,
            "is_expired": False,
            "is_about_to_expire": False,
            "error": f"无法解析日期格式: {expire_str}",
        }

    today = date.today()
    delta = (expire_date - today).days

    if delta <= 0:
        status = "已过期"
        is_expired = True
        is_about_to_expire = False
    elif delta <= 30:
        status = "三十天内即将过期"
        is_expired = False
        is_about_to_expire = True
    else:
        status = "未过期"
        is_expired = False
        is_about_to_expire = False

    return {
        "expire_date_str": expire_str,
        "status": status,
        "days_remaining": delta,
        "is_expired": is_expired,
        "is_about_to_expire": is_about_to_expire,
    }


def _do_validate(db_conn, parsed: dict[str, str], field_map: dict[str, str], table_name: str = "certification_test") -> dict:
    """
    内部函数：执行实际的数据库查询和字段比对
    db_conn 可以是 sqlite3.Connection 或 pymysql.connection
    """
    import sqlite3

    cursor = db_conn.cursor()
    is_sqlite = isinstance(db_conn, sqlite3.Connection)

    # ----- 4. 检查表是否存在，获取所有列名 -----
    if is_sqlite:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}
    else:
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = {row["Field"] for row in cursor.fetchall()}

    if not columns:
        raise ValueError(f"表 '{table_name}' 不存在或没有字段")

    # ----- 5. 找出映射中需要的数据库列，检查是否存在 -----
    reverse_map = {}  # 识别字段 → 数据库列
    for cn_field, db_col in field_map.items():
        if cn_field in parsed:
            if db_col not in columns:
                print(f"⚠️  映射字段 '{cn_field}' → '{db_col}' 在表中不存在，跳过")
                continue
            reverse_map[cn_field] = db_col

    if not reverse_map:
        raise ValueError(
            f"字段映射中的列在表 '{table_name}' 中都找不到，请检查映射配置"
        )

    db_columns_needed = list(set(reverse_map.values()))
    col_list = ", ".join(db_columns_needed)

    # ----- 6. 查询数据库记录 -----
    # 优先用公司名称匹配
    company_name = (
        parsed.get("公司名称")
        or parsed.get("经营者名称")
        or parsed.get("生产者名称")
    )

    if company_name:
        if is_sqlite:
            cursor.execute(
                f"SELECT {col_list} FROM {table_name} WHERE company_name LIKE ? LIMIT 1",
                (f"%{company_name}%",),
            )
        else:
            cursor.execute(
                f"SELECT {col_list} FROM {table_name} WHERE company_name LIKE %s LIMIT 1",
                (f"%{company_name}%",),
            )
        db_record = cursor.fetchone()
    else:
        # 没有公司名称，直接取第一条记录
        cursor.execute(f"SELECT {col_list} FROM {table_name} LIMIT 1")
        db_record = cursor.fetchone()
        print("ℹ️  识别结果中未找到公司名称，已取表中第一条记录对比")

    if not db_record:
        # 记录不存在 → 所有字段标记不匹配
        details = [
            {
                "field": cn_field,
                "db_column": db_col,
                "recognized": parsed.get(cn_field, ""),
                "expected": None,
                "match": False,
                "reason": "数据库中未找到匹配记录",
            }
            for cn_field, db_col in reverse_map.items()
        ]
        return {
            "is_match": False,
            "matched_count": 0,
            "total_count": len(reverse_map),
            "match_ratio": 0.0,
            "db_record_found": False,
            "details": details,
        }

    # 将数据库记录转为普通字典
    if is_sqlite:
        db_record = dict(db_record)

    # ----- 7. 逐字段比对 -----
    details = []
    matched = 0
    for cn_field, db_col in reverse_map.items():
        recog_val = parsed.get(cn_field, "").strip()
        db_val = str(db_record.get(db_col, "") or "").strip()

        is_match = recog_val == db_val
        if is_match:
            matched += 1

        details.append({
            "field": cn_field,
            "db_column": db_col,
            "recognized": recog_val,
            "expected": db_val,
            "match": is_match,
        })

    total = len(details)
    all_match = matched == total
    ratio = matched / total if total > 0 else 0.0

    # ----- 8. 识别证照效期状态 -----
    EXPIRE_FIELDS = ["证件到效日期", "有效期截止日期", "营业期限截止日期", "有效截止日期"]
    expire_check = None
    for field in EXPIRE_FIELDS:
        if field in parsed:
            expire_check = check_expire_date(parsed[field])
            if expire_check["status"] != "未知":
                icon = {"已过期": "❌", "三十天内即将过期": "⚠️", "未过期": "✅"}
                print(f"📅 效期状态: {icon.get(expire_check['status'], '')} {expire_check['status']}（剩余 {expire_check['days_remaining']} 天）")
            break

    status = "✅ 完全匹配" if all_match else f"⚠️  部分匹配 ({matched}/{total})"
    print(f"{status}，匹配率: {ratio:.0%}")

    return {
        "is_match": all_match,
        "matched_count": matched,
        "total_count": total,
        "match_ratio": ratio,
        "db_record_found": True,
        "details": details,
        "expire_check": expire_check,
    }


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # ---------- 示例 1: 解析文本 PDF ----------
    # pages = parse_pdf_from_url("https://example.com/report.pdf")
    # for i, text in enumerate(pages):
    #     print(f"\n=== 第 {i+1} 页 ===")
    #     print(text[:500])

    # ---------- 示例 2: OCR 提取图片文字 ----------
    # text = parse_image_ocr("https://prd-sc-sofa.oss-cn-chengdu.aliyuncs.com/vss-web/8560/vendorApplyCertification/20240511/a8cea2de-ab23-4727-8141-544ad2db9880/5b38862b-a16e-47a7-a5e9-fefc43f2d532.jpg", lang="chi_sim+eng")
    # print(text)

    # ---------- 示例 3: Mimo 多模态理解图片 ----------
    text = parse_with_multimodal(
        # "https://prd-sc-sofa.oss-cn-chengdu.aliyuncs.com/vss-web/8560/vendorApplyCertification/20240511/a8cea2de-ab23-4727-8141-544ad2db9880/5b38862b-a16e-47a7-a5e9-fefc43f2d532.jpg",
       "https://prd-sc-sofa.oss-cn-chengdu.aliyuncs.com/vss-web/8560/certification/20231130/487b2445-d8f1-4e01-98b1-8a9639ac6546/%E7%94%9F%E4%BA%A7%E8%AE%B8%E5%8F%AF%E8%AF%81.jpg",
        prompt="""
        请识别图片中的内容，例如：1.证照类型：营业执照、食品经营许可证、食品生产许可证、商品批次报告、第三方检验报告；
               2.识别公司名称：如营业执照的名称、食品经营许可证的经营者名称、食品生产许可证的生产者名称；
               3.识别证件到效日期：如营业执照的营业期限截止日期、食品经营许可证的有效期截止日期、食品生产许可证的有效日期截止日期（若截止日日期为长期，则输出为2099-01-01）
         """,
    )
    print("=" * 60)
    print("识别结果:")
    print(text)

    # ---------- 示例 5: 测试数据库校验（test_mode=True）----------
    print("\n" + "=" * 60)
    print("测试数据库校验 (test_mode=True)")

    # 模拟一个识别结果（格式与 Mimo 返回一致）
    mock_text = """
    1. 证照类型：食品生产许可证
    2. 生产者名称：贵州益佰制药股份有限公司
    3. 统一社会信用代码：91520000214304865U
    4. 有效期截止日期：2027-11-30
    """
    result = validate_with_db(mock_text, test_mode=True)

    print(f"\n校验结果: {'✅ 通过' if result['is_match'] else '❌ 不通过'}")
    print(f"匹配率: {result['match_ratio']:.0%} ({result['matched_count']}/{result['total_count']})")
    for d in result["details"]:
        icon = "✅" if d["match"] else "❌"
        print(f"  {icon} {d['field']}: 识别=「{d['recognized']}」 期望=「{d['expected']}」")

    # 效期校验结果
    if result.get("expire_check"):
        ec = result["expire_check"]
        icon_map = {"未过期": "✅", "三十天内即将过期": "⚠️", "已过期": "❌", "未知": "❓"}
        print(f"  📅 效期: {icon_map.get(ec['status'], '')} {ec['status']}（剩余 {ec['days_remaining']} 天）")

    # ---------- 示例 5b: 效期规则演示 ----------
    print("\n" + "=" * 60)
    print("效期规则演示:")
    from datetime import date, timedelta
    today = date.today()

    test_dates = [
        (today - timedelta(days=10)).strftime("%Y-%m-%d"),   # 已过期
        (today + timedelta(days=15)).strftime("%Y-%m-%d"),   # 三十天内
        (today + timedelta(days=365)).strftime("%Y-%m-%d"),  # 未过期
        "2099-01-01",                                         # 长期有效
        today.strftime("%Y-%m-%d"),                            # 今天到期
    ]
    for d in test_dates:
        ec = check_expire_date(d)
        icon_map = {"未过期": "✅", "三十天内即将过期": "⚠️", "已过期": "❌", "未知": "❓"}
        print(f"  {icon_map.get(ec['status'], '')} {d} → {ec['status']}（{ec['days_remaining']} 天）")

    # ---------- 示例 6: 用真实识别结果校验（取消注释即可运行）----------
    # print("\n" + "=" * 60)
    # print("用真实识别结果校验")
    # result = validate_with_db(text, test_mode=True)
    # print(f"校验结果: {'✅ 通过' if result['is_match'] else '❌ 不通过'}")
    # for d in result["details"]:
    #     icon = "✅" if d["match"] else "❌"
    #     print(f"  {icon} {d['field']}: 识别=「{d['recognized']}」 期望=「{d['expected']}」")
    # if result.get("expire_check"):
    #     ec = result["expire_check"]
    #     print(f"  📅 {ec['status']}（剩余 {ec['days_remaining']} 天）")

    # ---------- 示例 7: MySQL 模式（填好 MYSQL_CONFIG 后取消注释）----------
    # print("\n" + "=" * 60)
    # print("MySQL 校验")
    # result = validate_with_db(text, test_mode=False, table_name="实际表名")
    # print(result)
