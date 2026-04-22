import os
import shutil
import sys
from typing import Dict, List

from app_version import APP_NAME

_RUNTIME_DIRS = ["log", "html", "RSS", "Paper", "SI"]
_DEFAULT_FILES = [
    "DomainBranch.json",
    "DownloadSettings.json",
    "DownloadTemplates.json",
    "LoginConfig.json",
    "onboarding.json",
    "Paperkeyword.json",
    "SIkeyword.json",
    "initial_tabs.json",
    "PaperDoi.csv",
    "input.txt",
]


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> str:
    if is_frozen_app() and hasattr(sys, "_MEIPASS"):
        return str(getattr(sys, "_MEIPASS"))
    return os.path.dirname(os.path.abspath(__file__))


def get_app_dir() -> str:
    if is_frozen_app():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir() -> str:
    override = os.environ.get("AUTOPAPERDOWNLOAD_DATA_DIR", "").strip()
    if override:
        resolved = os.path.abspath(os.path.expanduser(override))
        if sys.platform == "darwin":
            resolved = resolved.replace(
                "/Library/ApplicationSupport/",
                "/Library/Application Support/",
            )
        return resolved

    if not is_frozen_app():
        return os.path.dirname(os.path.abspath(__file__))

    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    return os.path.join(os.path.expanduser("~/.local/share"), APP_NAME)


def bundle_path(*parts: str) -> str:
    return os.path.join(get_bundle_dir(), *parts)


def app_path(*parts: str) -> str:
    return os.path.join(get_app_dir(), *parts)


def data_path(*parts: str) -> str:
    return os.path.join(get_data_dir(), *parts)


def get_log_dir() -> str:
    return data_path("log")


def _copy_default_files_if_missing(data_dir: str, bundle_dir: str) -> None:
    for filename in _DEFAULT_FILES:
        src = os.path.join(bundle_dir, filename)
        dst = os.path.join(data_dir, filename)
        if not os.path.exists(src) or os.path.exists(dst):
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        except Exception:
            continue


def ensure_runtime_layout() -> Dict[str, str]:
    data_dir = get_data_dir()
    bundle_dir = get_bundle_dir()

    os.makedirs(data_dir, exist_ok=True)
    for dirname in _RUNTIME_DIRS:
        os.makedirs(os.path.join(data_dir, dirname), exist_ok=True)

    _copy_default_files_if_missing(data_dir, bundle_dir)

    return {
        "bundle_dir": bundle_dir,
        "app_dir": get_app_dir(),
        "data_dir": data_dir,
        "log_dir": os.path.join(data_dir, "log"),
        "html_dir": os.path.join(data_dir, "html"),
        "rss_dir": os.path.join(data_dir, "RSS"),
        "paper_dir": os.path.join(data_dir, "Paper"),
        "si_dir": os.path.join(data_dir, "SI"),
    }


def default_runtime_dirs() -> List[str]:
    return list(_RUNTIME_DIRS)
