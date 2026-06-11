"""统一配置加载模块。"""

from __future__ import annotations

from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_config(filename: str) -> dict:
    """加载 configs/ 目录下的 YAML 配置。"""
    path = BASE_DIR / "configs" / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_semantic_config() -> dict:
    """加载语义配置。"""
    return load_config("semantic.yaml")


def load_prompts_config() -> dict:
    """加载提示词配置。"""
    return load_config("prompts.yaml")


def load_examples_config() -> list[dict]:
    """加载 NL2SQL 示例配置。"""
    data = load_config("examples.yaml")
    return data.get("examples", [])
