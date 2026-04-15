import os
import subprocess
import sys
from typing import Dict, List

from runtime_paths import app_path, get_app_dir, get_bundle_dir, is_frozen_app

SCRIPT_KEY_TO_FILE: Dict[str, str] = {
    "getdoi": "getdoi_helper.py",
    "paper": "Paperdownload.py",
    "si": "SIdownload.py",
    "clean": "clean_worker.py",
    "csv_turner": "Csv_Turner_strenth.py",
    "doiexacter": "doiexacter.py",
}

WORKER_KEY_TO_NAME: Dict[str, str] = {
    "getdoi": "getdoi_worker",
    "paper": "paper_worker",
    "si": "si_worker",
    "clean": "clean_worker",
    "csv_turner": "csv_turner_worker",
    "doiexacter": "doiexacter_worker",
}


def script_name_for_key(script_key: str) -> str:
    if script_key in SCRIPT_KEY_TO_FILE:
        return SCRIPT_KEY_TO_FILE[script_key]
    return script_key


def resolve_worker_command(script_key: str) -> List[str]:
    if script_key not in SCRIPT_KEY_TO_FILE:
        raise KeyError(f"Unknown script key: {script_key}")

    if is_frozen_app():
        suffix = ".exe" if os.name == "nt" else ""
        worker_name = WORKER_KEY_TO_NAME[script_key] + suffix
        candidates: List[str] = []

        # macOS: prefer onedir workers stored under Contents/Workers/<worker>/<worker>
        if sys.platform == "darwin":
            # Handles both launch contexts:
            # 1) main app executable: .../Contents/MacOS/AutoPaperdownload
            # 2) worker executable:   .../Contents/Workers/getdoi_worker/getdoi_worker
            exe_dir = os.path.abspath(get_app_dir())
            candidates.append(os.path.normpath(os.path.join(exe_dir, "..", "Workers", worker_name, worker_name)))
            candidates.append(os.path.normpath(os.path.join(exe_dir, "..", worker_name, worker_name)))

            # Robust fallback: derive "/Contents" from sys.executable directly.
            marker = f"{os.sep}Contents{os.sep}"
            exe_path = os.path.abspath(sys.executable)
            if marker in exe_path:
                prefix, _ = exe_path.split(marker, 1)
                contents_dir = os.path.join(prefix, "Contents")
                candidates.append(os.path.normpath(os.path.join(contents_dir, "Workers", worker_name, worker_name)))
                candidates.append(os.path.normpath(os.path.join(contents_dir, "MacOS", worker_name)))

        # Legacy layout / Windows: worker binary directly under app dir
        candidates.append(app_path(worker_name))
        candidates.append(app_path("Workers", worker_name, worker_name))

        # de-duplicate while preserving order
        deduped: List[str] = []
        seen = set()
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)

        for worker_path in deduped:
            if os.path.exists(worker_path):
                return [worker_path]

        raise FileNotFoundError(
            "打包worker不存在，已检查: " + ", ".join(deduped)
        )

    script_path = os.path.join(get_bundle_dir(), SCRIPT_KEY_TO_FILE[script_key])
    return [sys.executable, script_path]


def spawn_worker(script_key: str, **popen_kwargs) -> subprocess.Popen:
    cmd = resolve_worker_command(script_key)
    return subprocess.Popen(cmd, **popen_kwargs)


def run_worker_blocking(script_key: str, **run_kwargs) -> subprocess.CompletedProcess:
    cmd = resolve_worker_command(script_key)
    return subprocess.run(cmd, **run_kwargs)
