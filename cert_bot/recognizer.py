"""
企业微信证照机器人 — 识别引擎封装

加载 Untitled-1.py 中的识别函数，提供统一调用接口
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional


def _load_untitled_module():
    """
    动态加载 Untitled-1.py（文件名含连字符，无法用常规 import）
    只加载一次，后续复用
    """
    module_path = Path(__file__).resolve().parent.parent / "Untitled-1.py"
    if not module_path.exists():
        raise FileNotFoundError(f"找不到 Untitled-1.py: {module_path}")

    spec = importlib.util.spec_from_file_location("untitled_module", str(module_path))
    mod = importlib.util.module_from_spec(spec)
    # 防止 __main__ 中的测试代码被执行
    mod.__name__ = "untitled_module"
    spec.loader.exec_module(mod)
    return mod


# 模块级缓存（首次调用时加载）
_module = None


def _get_module():
    global _module
    if _module is None:
        print("[recognizer] 加载识别引擎: Untitled-1.py")
        _module = _load_untitled_module()
    return _module


def parse_with_multimodal(
    file_url: str,
    prompt: str = "请提取这张图片/文档中的所有文字信息",
    api_key: Optional[str] = None,
) -> str:
    """
    用 Mimo V2.5 多模态模型识别图片/文档
    等效于 Untitled-1.parse_with_multimodal()
    """
    mod = _get_module()
    return mod.parse_with_multimodal(file_url, prompt, api_key)


def parse_recognized_text(text: str) -> dict:
    """
    将识别文本解析为结构化字典
    等效于 Untitled-1.parse_recognized_text()
    """
    mod = _get_module()
    return mod.parse_recognized_text(text)


def check_expire_date(expire_date_str: str) -> dict:
    """
    检查证照到期状态
    等效于 Untitled-1.check_expire_date()
    """
    mod = _get_module()
    return mod.check_expire_date(expire_date_str)
