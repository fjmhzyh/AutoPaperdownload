import os
import threading
import time

import psutil


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def start_parent_guard(check_interval_sec: float = 2.0, miss_limit: int = 2) -> None:
    """
    如果设置了 AUTOPAPERDOWNLOAD_PARENT_PID，则后台轮询父进程是否仍存活。
    父进程异常退出时，当前worker会自动退出，避免GUI崩溃后子脚本继续失控运行。
    """
    if _is_truthy(os.environ.get("AUTOPAPERDOWNLOAD_DISABLE_PARENT_GUARD", "")):
        return

    raw_pid = os.environ.get("AUTOPAPERDOWNLOAD_PARENT_PID", "").strip()
    if not raw_pid:
        return

    try:
        parent_pid = int(raw_pid)
    except ValueError:
        return

    if parent_pid <= 1:
        return

    def _watch_parent() -> None:
        misses = 0
        while True:
            alive = False
            try:
                proc = psutil.Process(parent_pid)
                alive = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                alive = False
            except Exception:
                # 未知异常时不立即退出，避免误杀；下一轮继续检查
                alive = True

            if alive:
                misses = 0
            else:
                misses += 1
                if misses >= max(1, miss_limit):
                    print(f"[进程守护] 检测到GUI进程已退出(PID={parent_pid})，当前脚本即将停止")
                    os._exit(190)

            time.sleep(max(0.5, check_interval_sec))

    threading.Thread(target=_watch_parent, daemon=True, name="parent-guard").start()

