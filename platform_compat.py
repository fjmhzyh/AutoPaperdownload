import os
import sys
import subprocess
import webbrowser
from typing import Dict, Tuple, List, Optional

import pyautogui


def is_windows() -> bool:
    return os.name == "nt"


def is_mac() -> bool:
    return sys.platform == "darwin"


def get_default_edge_browser_path() -> Optional[str]:
    if not is_windows():
        return None
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    return edge_path if os.path.exists(edge_path) else None


def resource_path(*parts: str, base_dir: Optional[str] = None) -> str:
    if base_dir:
        root = base_dir
    elif getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        root = str(getattr(sys, "_MEIPASS"))
    else:
        root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, *parts)


def get_browser_process_names() -> List[str]:
    if is_windows():
        return ["msedge.exe", "chrome.exe", "firefox.exe"]
    if is_mac():
        return [
            "microsoft edge",
            "microsoft edge helper",
            "google chrome",
            "google chrome helper",
            "safari",
            "firefox",
        ]
    return ["chrome", "chromium", "firefox", "edge", "safari"]


def open_url(url: str, browser_path: Optional[str] = None, new_window: bool = False) -> bool:
    try:
        if is_windows() and browser_path and os.path.exists(browser_path):
            subprocess.Popen([browser_path, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        if is_mac():
            subprocess.Popen(["open", url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        if new_window:
            return webbrowser.open_new(url)
        return webbrowser.open(url)
    except Exception:
        try:
            if new_window:
                return webbrowser.open_new(url)
            return webbrowser.open(url)
        except Exception:
            return False


def _hotkey_mapping() -> Dict[str, Tuple[str, ...]]:
    if is_mac():
        return {
            "focus_address_bar": ("command", "l"),
            "select_all": ("command", "a"),
            "copy": ("command", "c"),
            "view_source": ("command", "option", "u"),
            "print_page": ("command", "p"),
            "close_tab": ("command", "w"),
            "dismiss_dialog": ("esc",),
        }
    return {
        "focus_address_bar": ("alt", "d"),
        "select_all": ("ctrl", "a"),
        "copy": ("ctrl", "c"),
        "view_source": ("ctrl", "u"),
        "print_page": ("ctrl", "p"),
        "close_tab": ("ctrl", "w"),
        "dismiss_dialog": ("esc",),
    }


def hotkey(action_name: str) -> None:
    keys = _hotkey_mapping().get(action_name)
    if not keys:
        raise ValueError(f"Unknown hotkey action: {action_name}")
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
