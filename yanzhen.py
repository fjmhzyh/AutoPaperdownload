import pyautogui
import time
import random
import os
import math
import sys
import subprocess
from datetime import datetime
from typing import List, Optional, Tuple

# === ⚙️ 配置区域 ===

# 模板图片名（按顺序优先）
IMAGE_NAMES = ["target.png","target.jpeg", "target.jpg"]

# 分级匹配阈值
PRIMARY_CONFIDENCE_LEVELS = [0.93, 0.90, 0.87]
SECONDARY_CONFIDENCE_LEVELS = [0.85, 0.80]

# 点击随机偏移（越小越精准）
CLICK_OFFSET_PIXELS = 1

# 精准点击模式：直接点击识别框中心，不做拟人偏移
PRECISE_CLICK_MODE = True
PRECISE_MOVE_DURATION = 0.08

# 点击后复检参数（目标仍在则补点一次）
POST_CLICK_VERIFY_DELAY = 0.35
POST_CLICK_VERIFY_CONFIDENCE = 0.84
POST_CLICK_RETRY_MAX = 1

# 局部搜索区域（上次命中后优先在附近找）
LOCAL_REGION_PADDING = 220

# 是否启用灰度兜底（可能增加误识别率）
ENABLE_GRAYSCALE_FALLBACK = False

# 浏览器优先定位：尽量只在前台窗口内搜索（mac）
BROWSER_ONLY_MODE = True

# 过滤屏幕底部误命中（例如 Dock、状态条）
BOTTOM_REJECT_RATIO = 0.12

# 前台窗口裁剪（去掉浏览器工具栏和底部）
FRONT_WINDOW_TOP_CROP = 90
FRONT_WINDOW_BOTTOM_CROP = 20

# 检测频率 (秒)
CHECK_INTERVAL = 0.5       

# ⚠️【关键修改】搜索区域设置
# 如果你的屏幕很大（4K）或遇到内存报错，请取消下面元组的注释，填入大概的坐标范围
# 格式：(左边距, 上边距, 宽度, 高度)
# 例如：SEARCH_REGION = (0, 0, 1920, 1080)  # 只在左上角的 1920x1080 区域找
SEARCH_REGION = None 

# ====================

# 关闭 PyAutoGUI 的角落自动报错机制（防止鼠标随机移动到边缘时程序崩溃）
pyautogui.FAILSAFE = False
_BROWSER_REGION_WARNED = False

def log(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {message}")


def _unique_existing_paths(paths: List[str]) -> List[str]:
    seen = set()
    result = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        if os.path.exists(p):
            result.append(p)
    return result


def get_image_candidates() -> List[str]:
    """获取模板图片候选路径（mac优先photos/mac）"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dirs = []

    if sys.platform == "darwin":
        dirs.extend(
            [
                os.path.join(current_dir, "photos", "mac"),
                os.path.join(current_dir, "mac"),
            ]
        )

    # 兼容原有路径
    dirs.extend(
        [
            current_dir,
            os.path.join(current_dir, "photos"),
        ]
    )

    candidates = []
    for d in dirs:
        for image_name in IMAGE_NAMES:
            candidates.append(os.path.join(d, image_name))
    return _unique_existing_paths(candidates)


def _build_local_region(location, padding=LOCAL_REGION_PADDING):
    """根据命中框构造局部搜索区域"""
    if not location:
        return None
    left, top, width, height = location
    screen_w, screen_h = pyautogui.size()
    x1 = max(0, int(left - padding))
    y1 = max(0, int(top - padding))
    x2 = min(screen_w, int(left + width + padding))
    y2 = min(screen_h, int(top + height + padding))
    return (x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def _locate_with_strategy(
    image_paths: List[str],
    region,
    grayscale: bool,
    confidence_levels: List[float],
):
    for conf in confidence_levels:
        for image_path in image_paths:
            try:
                location = pyautogui.locateOnScreen(
                    image_path,
                    confidence=conf,
                    grayscale=grayscale,
                    region=region,
                )
                if location:
                    if _is_false_bottom_hit(location):
                        log("检测到疑似底部误命中，已忽略", level="WARN")
                        continue
                    return location, image_path, conf, grayscale, region
            except pyautogui.ImageNotFoundException:
                pass
            except Exception as e:
                log(f"识别异常: {e}", level="WARN")
    return None, None, None, None, None


def locate_target(image_paths: List[str], local_region=None):
    """
    分阶段识别：
    1) 上次命中附近（彩色，高阈值）
    2) 全局配置区域/全屏（彩色，高阈值）
    3) 全局配置区域/全屏（灰度，低阈值）
    """
    search_region = _get_effective_search_region()
    if local_region:
        hit = _locate_with_strategy(
            image_paths=image_paths,
            region=local_region,
            grayscale=False,
            confidence_levels=PRIMARY_CONFIDENCE_LEVELS,
        )
        if hit[0]:
            return hit

    hit = _locate_with_strategy(
        image_paths=image_paths,
        region=search_region,
        grayscale=False,
        confidence_levels=PRIMARY_CONFIDENCE_LEVELS,
    )
    if hit[0]:
        return hit

    if not ENABLE_GRAYSCALE_FALLBACK:
        return None, None, None, None, None

    return _locate_with_strategy(
        image_paths=image_paths,
        region=search_region,
        grayscale=True,
        confidence_levels=SECONDARY_CONFIDENCE_LEVELS,
    )


def _is_false_bottom_hit(location) -> bool:
    """过滤明显位于屏幕底部的误命中"""
    try:
        _, screen_h = pyautogui.size()
        center_y = location.top + location.height // 2
        return center_y > int(screen_h * (1 - BOTTOM_REJECT_RATIO))
    except Exception:
        return False


def _parse_osascript_bounds(output: str) -> Optional[Tuple[int, int, int, int]]:
    raw = (output or "").strip().replace("\n", "")
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        return None
    try:
        x, y, w, h = [int(float(v)) for v in parts]
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return x, y, w, h


def _get_front_window_region_mac() -> Optional[Tuple[int, int, int, int]]:
    """
    获取mac前台窗口区域（需要系统辅助功能权限）。
    返回 (x, y, w, h)，失败返回 None。
    """
    script = (
        'tell application "System Events"\n'
        "set frontApp to first application process whose frontmost is true\n"
        "set p to position of front window of frontApp\n"
        "set s to size of front window of frontApp\n"
        "return (item 1 of p) & \",\" & (item 2 of p) & \",\" & (item 1 of s) & \",\" & (item 2 of s)\n"
        "end tell"
    )
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if completed.returncode != 0:
            return None
        bounds = _parse_osascript_bounds(completed.stdout)
        if not bounds:
            return None
        x, y, w, h = bounds
        y2 = y + FRONT_WINDOW_TOP_CROP
        h2 = h - FRONT_WINDOW_TOP_CROP - FRONT_WINDOW_BOTTOM_CROP
        if h2 <= 40:
            return bounds
        return (x, y2, w, h2)
    except Exception:
        return None


def _get_effective_search_region():
    """
    实际搜索区域：
    1) 若用户手动设置 SEARCH_REGION，优先使用；
    2) mac + BROWSER_ONLY_MODE 时，优先前台窗口区域；
    3) 否则全屏。
    """
    if SEARCH_REGION:
        return SEARCH_REGION
    if sys.platform == "darwin" and BROWSER_ONLY_MODE:
        region = _get_front_window_region_mac()
        if region:
            return region
        global _BROWSER_REGION_WARNED
        if not _BROWSER_REGION_WARNED:
            _BROWSER_REGION_WARNED = True
            log("未能获取前台窗口区域，将退回全屏搜索", level="WARN")
            log("请在 mac 系统设置中为终端/Python开启“辅助功能”权限", level="WARN")
    return None

def get_bezier_point(t, p0, p1, p2, p3):
    """计算三阶贝塞尔曲线上的点"""
    u = 1 - t
    tt = t * t
    uu = u * u
    uuu = u * u * u
    ttt = tt * t
    
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    return (x, y)

def human_move(target_x, target_y, duration):
    """
    拟人化移动核心逻辑：
    生成随机贝塞尔曲线，并配合缓动算法（起步快，终点慢）
    """
    start_x, start_y = pyautogui.position()
    dist = math.hypot(target_x - start_x, target_y - start_y)
    
    # 距离太近直接移动，不画曲线
    if dist < 50:
        pyautogui.moveTo(target_x, target_y, duration=duration, tween=pyautogui.easeOutQuad)
        return

    # 1. 设置随机控制点（产生弧度）
    offset = dist * random.uniform(0.2, 0.5)
    cp1_x = start_x + (target_x - start_x) * 0.3 + random.uniform(-offset, offset)
    cp1_y = start_y + (target_y - start_y) * 0.3 + random.uniform(-offset, offset)
    cp2_x = start_x + (target_x - start_x) * 0.7 + random.uniform(-offset, offset)
    cp2_y = start_y + (target_y - start_y) * 0.7 + random.uniform(-offset, offset)

    # 2. 沿曲线移动
    steps = int(duration * 60)
    if steps < 10: steps = 10
    
    old_pause = pyautogui.PAUSE
    pyautogui.PAUSE = 0  # 临时取消内部暂停，保证丝滑
    
    start_time = time.time()
    
    for i in range(steps + 1):
        progress = i / steps
        # 二次缓出算法 (Ease Out): 接近终点时减速
        eased_progress = 1 - (1 - progress) * (1 - progress)
        
        x, y = get_bezier_point(
            eased_progress, 
            (start_x, start_y), 
            (cp1_x, cp1_y), 
            (cp2_x, cp2_y), 
            (target_x, target_y)
        )
        
        pyautogui.moveTo(x, y)
        
        # 简单的帧率控制
        elapsed = time.time() - start_time
        expected = duration * progress
        if expected > elapsed:
            time.sleep(expected - elapsed)

    # 3. 最终修正
    pyautogui.moveTo(target_x, target_y)
    pyautogui.PAUSE = old_pause

def simulate_human_click(location):
    """模拟人类点击流程"""
    if location:
        x, y = pyautogui.center(location)

        if PRECISE_CLICK_MODE:
            final_x = int(x)
            final_y = int(y)
            log(f"发现目标，执行精准点击: ({final_x}, {final_y})")
            pyautogui.moveTo(final_x, final_y, duration=PRECISE_MOVE_DURATION)
            pyautogui.click(final_x, final_y)
            return True

        # 非精准模式：保留拟人化逻辑
        final_x = x + random.randint(-CLICK_OFFSET_PIXELS, CLICK_OFFSET_PIXELS)
        final_y = y + random.randint(-CLICK_OFFSET_PIXELS, CLICK_OFFSET_PIXELS)
        log(f"发现目标，坐标: ({final_x}, {final_y})，开始拟人移动")
        move_time = random.uniform(0.5, 1.2)
        human_move(final_x, final_y, duration=move_time)
        time.sleep(random.uniform(0.1, 0.2))
        pyautogui.click(final_x, final_y)
        return True
    return False


def _target_still_visible(image_path: str, region) -> Optional[Tuple[int, int, int, int]]:
    try:
        return pyautogui.locateOnScreen(
            image_path,
            confidence=POST_CLICK_VERIFY_CONFIDENCE,
            grayscale=True,
            region=region,
        )
    except pyautogui.ImageNotFoundException:
        return None
    except Exception as e:
        log(f"点击后复检异常: {e}", level="WARN")
        return None

def main():
    image_paths = get_image_candidates()
    
    print("=" * 48)
    log("验证码自动点击器启动")
    log(f"系统平台: {sys.platform}")
    log(f"监听图片名候选: {IMAGE_NAMES}")
    log(f"主阈值: {PRIMARY_CONFIDENCE_LEVELS}")
    log(f"次阈值: {SECONDARY_CONFIDENCE_LEVELS}")
    log(f"精准点击模式: {PRECISE_CLICK_MODE}")
    log(f"灰度兜底: {ENABLE_GRAYSCALE_FALLBACK}")
    log(f"浏览器优先定位: {BROWSER_ONLY_MODE}")
    log(f"底部误命中过滤比例: {BOTTOM_REJECT_RATIO}")
    log(f"检测间隔: {CHECK_INTERVAL}s")
    effective_region = _get_effective_search_region()
    if effective_region:
        log(f"实际搜索区域: {effective_region}")
    else:
        log("实际搜索区域: 全屏")
    if image_paths:
        log(f"可用模板数量: {len(image_paths)}")
        for idx, p in enumerate(image_paths, 1):
            log(f"模板{idx}: {p}")
    else:
        log("可用模板数量: 0", level="WARN")
    log("停止运行请按 Ctrl+C")
    print("=" * 48)
    
    if not image_paths:
        expected = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "photos",
            "mac" if sys.platform == "darwin" else "",
        )
        log("找不到可用图片文件", level="ERROR")
        log(f"请确认目录中存在以下任一文件: {IMAGE_NAMES}", level="ERROR")
        log(f"建议放置目录: {expected}", level="ERROR")
        log("请确认图片位于脚本目录、photos/ 或 photos/mac/ 下", level="ERROR")
        return

    loop_count = 0
    hit_count = 0
    local_region = None

    # --- 主循环结构优化 ---
    while True:
        try:
            loop_count += 1
            location, matched_image, matched_conf, matched_gray, matched_region = locate_target(
                image_paths,
                local_region=local_region,
            )
            
            # 2. 如果找到（没报错且不为None），执行点击
            if location:
                hit_count += 1
                previous_local_region = local_region
                local_region = _build_local_region(location)
                region_label = "局部区域" if matched_region == previous_local_region else "全局区域"
                mode_label = "灰度" if matched_gray else "彩色"
                log(
                    f"第 {loop_count} 次检测命中，第 {hit_count} 次点击 | "
                    f"模式={mode_label} 阈值={matched_conf} 区域={region_label}"
                )
                log(f"命中模板: {matched_image}")
                simulate_human_click(location)

                # 点击后复检：若目标仍在，补点一次
                verify_region = _build_local_region(location, padding=140)
                retry_count = 0
                while retry_count < POST_CLICK_RETRY_MAX:
                    time.sleep(POST_CLICK_VERIFY_DELAY)
                    if not matched_image:
                        break
                    remain = _target_still_visible(matched_image, verify_region)
                    if not remain:
                        break
                    retry_count += 1
                    log(f"点击后目标仍可见，执行补点 #{retry_count}", level="WARN")
                    simulate_human_click(remain)

                log("点击完成，进入冷却")
                time.sleep(random.uniform(2.5, 4.0))
            elif loop_count % 20 == 0:
                log(f"监听中... 已检测 {loop_count} 次，命中 {hit_count} 次")
                if loop_count % 120 == 0:
                    # 定期清理局部区域，防止局部区域漂移导致漏检
                    local_region = None
                    log("已重置局部搜索区域，回到全局扫描")
            
        except pyautogui.ImageNotFoundException:
            # 找不到图片是常态，直接跳过进入下一次循环
            pass
            
        except Exception as e:
            # ⚠️ 捕获所有其他严重错误（如内存溢出、文件被占等）
            # 这里不会退出程序，而是打印错误并重试
            log(f"发生异常: {e}", level="ERROR")
            log("程序将在 3 秒后重试", level="WARN")
            time.sleep(3)
        
        # 每次扫描后的间隔
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("用户手动停止程序", level="WARN")
