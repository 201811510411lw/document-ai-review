"""
企业微信证照机器人 — 数据库管理

SQLite 数据库（后续可切换 MySQL）
"""

import sqlite3
import os
from datetime import date, datetime
from typing import Optional
from . import config

# ============================================================
# 数据库初始化
# ============================================================

def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    db_path = config.DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # 提升并发性能
    return conn


def init_db():
    """创建表结构（幂等）"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certification_records (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name        TEXT NOT NULL,
            license_type        TEXT,
            credit_code         TEXT,
            expire_date         TEXT,
            legal_person        TEXT,
            address             TEXT,

            -- 识别元数据
            raw_recognized_text TEXT,
            source_file_url     TEXT,
            source_file_name    TEXT,

            -- 效期状态（定期更新）
            expire_status       TEXT DEFAULT 'unknown',
            expire_days_remaining INTEGER,
            last_checked_date   TEXT,

            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_batches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_no        TEXT UNIQUE,
            total_count     INTEGER DEFAULT 0,
            success_count   INTEGER DEFAULT 0,
            fail_count      INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 索引：加速按公司名搜索和按效期筛选
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_company ON certification_records(company_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_expire ON certification_records(expire_status, expire_days_remaining)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_records_created ON certification_records(created_at)")

    conn.commit()
    conn.close()


# ============================================================
# CRUD 操作
# ============================================================

def save_record(
    company_name: str,
    license_type: str = "",
    credit_code: str = "",
    expire_date: str = "",
    legal_person: str = "",
    address: str = "",
    raw_text: str = "",
    source_url: str = "",
    source_name: str = "",
) -> int:
    """
    保存一条证照识别记录
    返回记录 ID
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 计算效期状态
    expire_status, days_remaining = _calc_expire_status(expire_date)

    cursor.execute("""
        INSERT INTO certification_records
            (company_name, license_type, credit_code, expire_date,
             legal_person, address, raw_recognized_text,
             source_file_url, source_file_name,
             expire_status, expire_days_remaining, last_checked_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        company_name, license_type, credit_code, expire_date,
        legal_person, address, raw_text,
        source_url, source_name,
        expire_status, days_remaining, date.today().isoformat(),
    ))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def update_record(record_id: int, **kwargs):
    """
    更新记录字段
    用法: update_record(1, license_type="营业执照", expire_date="2028-01-01")
    """
    allowed = {
        "company_name", "license_type", "credit_code", "expire_date",
        "legal_person", "address", "raw_recognized_text",
        "source_file_url", "source_file_name",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return

    # 如果更新了 expire_date，重新计算状态
    if "expire_date" in updates:
        expire_status, days_remaining = _calc_expire_status(updates["expire_date"])
        updates["expire_status"] = expire_status
        updates["expire_days_remaining"] = days_remaining
        updates["last_checked_date"] = date.today().isoformat()

    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [record_id]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE certification_records SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def search_records(keyword: str) -> list:
    """
    按公司名模糊搜索
    返回匹配记录列表
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM certification_records WHERE company_name LIKE ? ORDER BY created_at DESC",
        (f"%{keyword}%",),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_record(record_id: int) -> Optional[dict]:
    """按 ID 查询单条记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM certification_records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_records(limit: int = 100, offset: int = 0) -> list:
    """获取所有记录（分页）"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM certification_records ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_expiring_records(days: int = 30) -> list:
    """
    获取在指定天数内即将过期的记录
    days: 剩余天数阈值（默认 30 天）
    返回 expire_days_remaining 在 [0, days] 之间的记录
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM certification_records
           WHERE expire_days_remaining >= 0 AND expire_days_remaining <= ?
           ORDER BY expire_days_remaining ASC""",
        (days,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_expired_records() -> list:
    """获取已过期记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM certification_records
           WHERE expire_status = 'expired'
           ORDER BY expire_days_remaining ASC""",
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def refresh_all_expire_status():
    """
    刷新所有记录的效期状态（定时任务调用）
    返回 (total, updated) 计数
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, expire_date FROM certification_records")
    rows = cursor.fetchall()
    today = date.today()

    updated = 0
    for row in rows:
        record_id = row["id"]
        expire_str = row["expire_date"]
        if not expire_str:
            continue

        status, days = _calc_expire_status(expire_str)
        cursor.execute(
            """UPDATE certification_records
               SET expire_status = ?, expire_days_remaining = ?, last_checked_date = ?, updated_at = ?
               WHERE id = ?""",
            (status, days, today.isoformat(), datetime.now().isoformat(), record_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    return len(rows), updated


def delete_record(record_id: int) -> bool:
    """删除记录"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM certification_records WHERE id = ?", (record_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_stats() -> dict:
    """获取统计信息"""
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}
    cursor.execute("SELECT COUNT(*) FROM certification_records")
    stats["total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM certification_records WHERE expire_status = 'valid'")
    stats["valid"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM certification_records WHERE expire_status = 'expiring_soon'")
    stats["expiring_soon"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM certification_records WHERE expire_status = 'expired'")
    stats["expired"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM certification_records WHERE expire_status = 'unknown'")
    stats["unknown"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM import_batches")
    stats["batches"] = cursor.fetchone()[0]

    conn.close()
    return stats


# ============================================================
# 导入批次管理
# ============================================================

def create_import_batch(batch_no: str) -> int:
    """创建导入批次，返回批次 ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO import_batches (batch_no) VALUES (?)", (batch_no,))
    batch_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return batch_id


def update_import_batch(batch_id: int, success_count: int, fail_count: int):
    """更新导入批次统计"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE import_batches SET success_count = ?, fail_count = ? WHERE id = ?",
        (success_count, fail_count, batch_id),
    )
    conn.commit()
    conn.close()


# ============================================================
# 内部辅助
# ============================================================

def _calc_expire_status(expire_str: str) -> tuple[str, int]:
    """
    根据日期字符串计算效期状态
    返回 (status, days_remaining)
    """
    from datetime import date

    if not expire_str or expire_str.strip() in ("长期", "永久", "长期有效", "2099-01-01"):
        return ("valid", 99999)

    try:
        expire_date = datetime.strptime(expire_str.strip(), "%Y-%m-%d").date()
        today = date.today()
        delta = (expire_date - today).days
    except ValueError:
        return ("unknown", 99999)

    if delta <= 0:
        return ("expired", delta)
    elif delta <= 30:
        return ("expiring_soon", delta)
    else:
        return ("valid", delta)
