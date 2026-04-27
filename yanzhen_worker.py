import os
import runpy
import sys

import image_resolver  # noqa: F401  # 强制打包该模块，供 yanzhen.py 运行时导入
from runtime_paths import data_path, ensure_runtime_layout, get_bundle_dir


def _resolve_yanzhen_script() -> str:
    ensure_runtime_layout()
    bundle_dir = get_bundle_dir()
    candidates = [
        os.path.join(bundle_dir, "photos", "yanzhen.py"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos", "yanzhen.py"),
        data_path("photos", "yanzhen.py"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(f"yanzhen.py not found, checked: {', '.join(candidates)}")


def main() -> None:
    script_path = _resolve_yanzhen_script()
    script_dir = os.path.dirname(script_path)
    if script_dir and script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    runpy.run_path(script_path, run_name="__main__")


if __name__ == "__main__":
    main()
