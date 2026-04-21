import os
import sys
import subprocess
import webbrowser
from typing import Dict, Tuple, List, Optional

import pyautogui

_last_open_url_error: str = ""


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
    global _last_open_url_error
    _last_open_url_error = ""
    try:
        if is_windows() and browser_path and os.path.exists(browser_path):
            subprocess.Popen([browser_path, url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        if is_mac():
            completed = subprocess.run(
                ["open", url],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if completed.returncode != 0:
                stderr_text = (completed.stderr or "").strip()
                stdout_text = (completed.stdout or "").strip()
                _last_open_url_error = stderr_text or stdout_text or f"open exit code={completed.returncode}"
                return False
            return True
        if new_window:
            return webbrowser.open_new(url)
        return webbrowser.open(url)
    except Exception as e:
        _last_open_url_error = str(e)
        try:
            if new_window:
                return webbrowser.open_new(url)
            return webbrowser.open(url)
        except Exception as fallback_e:
            _last_open_url_error = f"{_last_open_url_error}; fallback={fallback_e}"
            return False


def get_last_open_url_error() -> str:
    return _last_open_url_error


def _hotkey_mapping() -> Dict[str, Tuple[str, ...]]:
    if is_mac():
        return {
            "new_tab": ("command", "t"),
            "focus_address_bar": ("command", "l"),
            "refresh_page": ("command", "r"),
            "select_all": ("command", "a"),
            "copy": ("command", "c"),
            "paste": ("command", "v"),
            "go_to_folder": ("command", "shift", "g"),
            "view_source": ("command", "option", "u"),
            "print_page": ("command", "p"),
            "close_tab": ("command", "w"),
            "dismiss_dialog": ("esc",),
            "shift_tab":("shift","tab")
        }
    return {
        "new_tab": ("ctrl", "t"),
        "focus_address_bar": ("alt", "d"),
        "refresh_page": ("ctrl", "r"),
        "select_all": ("ctrl", "a"),
        "copy": ("ctrl", "c"),
        "paste": ("ctrl", "v"),
        "view_source": ("ctrl", "u"),
        "print_page": ("ctrl", "p"),
        "close_tab": ("ctrl", "w"),
        "dismiss_dialog": ("esc",),
        "shift_tab":("shift","tab")
    }


def hotkey(action_name: str) -> None:
    keys = _hotkey_mapping().get(action_name)
    # print(f"hotkey:{action_name}-{keys[0]}-{keys[1]}")
    if not keys:
        raise ValueError(f"Unknown hotkey action: {action_name}")
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def refresh_page() -> None:
    hotkey("refresh_page")
