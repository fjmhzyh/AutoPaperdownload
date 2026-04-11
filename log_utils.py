import logging
import os
import sys
from datetime import datetime
from typing import List, TextIO


_ACTIVE_LOG_HANDLES: List[TextIO] = []


class TeeStream:
    """将输出同时写入多个流（终端 + 日志文件）。"""

    def __init__(self, *streams: TextIO):
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            try:
                stream.write(data)
            except Exception:
                continue
        return len(data)

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                continue

    def isatty(self) -> bool:
        for stream in self.streams:
            try:
                if stream.isatty():
                    return True
            except Exception:
                continue
        return False


def setup_script_logging(script_file: str) -> str:
    """
    为脚本开启日志双写:
    - 控制台正常显示
    - 同时写入项目根目录/log/<script>_<timestamp>.log
    """
    script_path = os.path.abspath(script_file)
    base_dir = os.path.dirname(script_path)
    script_name = os.path.splitext(os.path.basename(script_path))[0]

    log_dir = os.path.join(base_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{script_name}_{timestamp}.log")

    file_stream = open(log_path, "a", encoding="utf-8", buffering=1)
    _ACTIVE_LOG_HANDLES.append(file_stream)

    sys.stdout = TeeStream(sys.stdout, file_stream)
    sys.stderr = TeeStream(sys.stderr, file_stream)

    # 已经初始化过的 logging StreamHandler 也切到新的 stderr，确保被日志文件捕获
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            try:
                handler.setStream(sys.stderr)
            except Exception:
                continue

    print(f"[日志] 运行日志文件: {log_path}")
    return log_path
