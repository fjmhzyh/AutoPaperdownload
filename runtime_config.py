import json
import os
from typing import Any, Dict

from runtime_paths import data_path, ensure_runtime_layout, get_data_dir

RUNTIME_CONFIG_FILE = "runtime_config.json"


def _default_config() -> Dict[str, Any]:
    data_dir = get_data_dir()
    return {
        "version": 1,
        "paths": {
            "DOWNLOAD_PATH": os.path.join(data_dir, "html"),
            "PAPER_FOLDER": os.path.join(data_dir, "Paper"),
            "SI_FOLDER": os.path.join(data_dir, "SI"),
            "CSV_PATH": os.path.join(data_dir, "PaperDoi.csv"),
            "CLEAN_FOLDER": os.path.join(data_dir, "Paper"),
            "CLEAN_CSV_IN": os.path.join(data_dir, "PaperDoi.csv"),
            "CLEAN_CSV_OUT": os.path.join(data_dir, "PaperDoi_updated_clean.csv"),
            "TURNER_IN": os.path.join(data_dir, "PaperDoi_updated.csv"),
            "TURNER_OUT": os.path.join(data_dir, "PaperDoi_failed.csv"),
            "EXACT_IN": os.path.join(data_dir, "input.txt"),
            "EXACT_OUT": os.path.join(data_dir, "PaperDoi.csv"),
        },
        "params": {
            "USE_SELENIUM": False,
            "DELAY_PAPER": 60,
            "DELAY_SI": 5,
            "TIMEOUT": 40,
            "CLEAN_THRESHOLD": 47,
            "SEARCH_QUERY": "(PCL) AND (Light curing)",
        },
    }


def get_runtime_config_path() -> str:
    return data_path(RUNTIME_CONFIG_FILE)


def _merge_two_levels(defaults: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(defaults)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _normalize_paths(config: Dict[str, Any]) -> Dict[str, Any]:
    paths = config.setdefault("paths", {})
    data_dir = get_data_dir()
    for key, raw in list(paths.items()):
        if not isinstance(raw, str) or not raw.strip():
            continue
        expanded = os.path.expanduser(raw.strip())
        if not os.path.isabs(expanded):
            expanded = os.path.join(data_dir, expanded)
        paths[key] = os.path.abspath(expanded)
    return config


def load_runtime_config() -> Dict[str, Any]:
    ensure_runtime_layout()
    path = get_runtime_config_path()
    defaults = _default_config()

    if not os.path.exists(path):
        save_runtime_config(defaults)
        return defaults

    try:
        with open(path, "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            loaded = {}
    except Exception:
        loaded = {}

    merged = _merge_two_levels(defaults, loaded)
    merged = _normalize_paths(merged)
    save_runtime_config(merged)
    return merged


def save_runtime_config(config: Dict[str, Any]) -> str:
    ensure_runtime_layout()
    merged = _merge_two_levels(_default_config(), config if isinstance(config, dict) else {})
    merged = _normalize_paths(merged)

    path = get_runtime_config_path()
    with open(path, "w", encoding="utf-8") as file:
        json.dump(merged, file, indent=2, ensure_ascii=False)
    return path
