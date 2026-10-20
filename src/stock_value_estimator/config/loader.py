from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}

def load(name: str) -> dict[str, Any]:
    with _LOCK:
        if name in _CACHE:
            return _CACHE[name]

        json_path = CONFIG_DIR / f"{name}.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8")) or {}
            _CACHE[name] = data
            return data

        yaml_path = CONFIG_DIR / f"{name}.yaml"
        if yaml_path.exists():
            try:
                import yaml
            except ImportError as e:
                raise FileNotFoundError(
                    f"配置文件缺失：{json_path}（且环境无 PyYAML 无法回退 {yaml_path}）"
                ) from e
            with yaml_path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _CACHE[name] = data
            return data

        raise FileNotFoundError(f"配置文件缺失：{json_path} / {yaml_path}")

def params() -> dict[str, Any]:
    return load("params")

def anchors() -> dict[str, Any]:
    return load("anchors")

def weights() -> dict[str, Any]:
    return load("weights")

def industry_map() -> dict[str, Any]:
    return load("industry_map")

def reload_all() -> None:
    with _LOCK:
        _CACHE.clear()

def get(section: str, key: str, default: Any = None) -> Any:
    node: Any = params()
    for part in section.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    if isinstance(node, dict):
        return node.get(key, default)
    return default
