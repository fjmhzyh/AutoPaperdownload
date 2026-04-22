import os
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

import pyautogui

DEFAULT_PROFILE_BY_OS = {
    "mac": "mac_1280_828",
    "win": "win_1920_1080",
}

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_PROFILE_LOGGED: set[str] = set()


def detect_os_family() -> str:
    """检测系统类型：非mac一律按win处理。"""
    return "mac" if sys.platform == "darwin" else "win"


def detect_screen_resolution() -> Optional[Tuple[int, int]]:
    """检测屏幕分辨率，失败返回None。"""
    try:
        size = pyautogui.size()
        width = int(getattr(size, "width", size[0]))
        height = int(getattr(size, "height", size[1]))
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception:
        return None


def _emit(message: str, logger: Any = None) -> None:
    if logger is None:
        print(message)
        return
    try:
        if hasattr(logger, "info"):
            logger.info(message)
        elif callable(logger):
            logger(message)
        else:
            print(message)
    except Exception:
        print(message)


def _resolve_photos_root(base_dir: Optional[str] = None) -> str:
    if base_dir:
        root = os.path.abspath(base_dir)
        if os.path.basename(root).lower() == "photos":
            return root
        return os.path.join(root, "photos")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")


def get_profile_info(base_dir: Optional[str] = None) -> Dict[str, Any]:
    photos_root = _resolve_photos_root(base_dir)
    cache_key = photos_root
    cached = _PROFILE_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    os_family = detect_os_family()
    resolution = detect_screen_resolution()
    if resolution is None:
        profile_folder = DEFAULT_PROFILE_BY_OS[os_family]
    else:
        profile_folder = f"{os_family}_{resolution[0]}_{resolution[1]}"

    profile_path = os.path.join(photos_root, profile_folder)
    info = {
        "os_family": os_family,
        "screen_resolution": resolution,
        "profile_folder": profile_folder,
        "photos_root": photos_root,
        "profile_path": profile_path,
    }
    _PROFILE_CACHE[cache_key] = info
    return dict(info)


def get_profile_folder(base_dir: Optional[str] = None) -> str:
    return str(get_profile_info(base_dir)["profile_folder"])


def resolve_image_path(
    image_name: str,
    base_dir: Optional[str] = None,
    logger: Any = None,
) -> Optional[str]:
    info = get_profile_info(base_dir)
    candidate = os.path.join(info["profile_path"], image_name)
    if os.path.isfile(candidate):
        return candidate
    _emit(
        f"[图片解析] 缺图: {image_name} profile={info['profile_folder']} path={candidate}",
        logger=logger,
    )
    return None


def log_profile_once(logger: Any = None, base_dir: Optional[str] = None) -> None:
    info = get_profile_info(base_dir)
    unique_key = f"{info['photos_root']}::{info['profile_folder']}"
    if unique_key in _PROFILE_LOGGED:
        return
    resolution = info["screen_resolution"]
    resolution_text = (
        f"{resolution[0]}x{resolution[1]}" if resolution else "unknown(default)"
    )
    _emit(
        "[图片解析] "
        f"os_family={info['os_family']} "
        f"screen_resolution={resolution_text} "
        f"image_profile_folder={info['profile_folder']} "
        f"profile_path={info['profile_path']}",
        logger=logger,
    )
    _PROFILE_LOGGED.add(unique_key)


def validate_required_images(
    required_images: Iterable[str],
    base_dir: Optional[str] = None,
    logger: Any = None,
) -> bool:
    missing = []
    for image_name in required_images:
        if resolve_image_path(image_name, base_dir=base_dir, logger=logger) is None:
            missing.append(image_name)
    if missing:
        _emit(
            f"[图片解析] 缺图清单: {', '.join(missing)}",
            logger=logger,
        )
        return False
    return True
