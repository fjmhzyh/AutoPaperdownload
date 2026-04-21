import pyautogui
import time
import random
import os
import math

# === ⚙️ 配置区域 ===

# 图片文件名
IMAGE_NAME = 'target.jpeg'

# 匹配相似度
CONFIDENCE = 0.8           

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

def get_image_path():
    """获取图片绝对路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    same_dir = os.path.join(current_dir, IMAGE_NAME)
    if os.path.exists(same_dir):
        return same_dir
    photos_dir = os.path.join(current_dir, "photos", IMAGE_NAME)
    return photos_dir

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
        
        # 目标点随机偏移 (防止总是点击同一个像素)
        final_x = x + random.randint(-5, 5)
        final_y = y + random.randint(-5, 5)
        
        print(f"✅ 发现目标！坐标: ({final_x}, {final_y})，正在移动...")
        
        # 随机耗时 (0.5 - 1.2秒)
        move_time = random.uniform(0.5, 1.2)
        
        # 执行拟人移动
        human_move(final_x, final_y, duration=move_time)
        
        # 模拟人类确认时的微小停顿
        time.sleep(random.uniform(0.1, 0.2))
        pyautogui.click()
        return True
    return False


def try_click_captcha(max_wait_seconds=8.0, confidence=None, search_region=None):
    """
    在限定时间内检测并尝试点击一次验证码目标。
    返回:
        True  -> 发现并点击了目标
        False -> 未发现目标或点击失败
    """
    target_path = get_image_path()
    if not os.path.exists(target_path):
        print(f"[验证码] 未找到目标图片: {target_path}")
        return False

    conf = CONFIDENCE if confidence is None else confidence
    region = SEARCH_REGION if search_region is None else search_region

    deadline = time.time() + max(0.1, float(max_wait_seconds))
    while time.time() < deadline:
        try:
            location = pyautogui.locateOnScreen(
                target_path,
                confidence=conf,
                grayscale=True,
                region=region,
            )
            if location:
                print("[验证码] 检测到验证码目标，尝试自动点击")
                clicked = simulate_human_click(location)
                if clicked:
                    print("[验证码] 自动点击完成")
                return clicked
        except pyautogui.ImageNotFoundException:
            pass
        except Exception as e:
            print(f"[验证码] 检测过程异常: {e}")
            return False

        time.sleep(CHECK_INTERVAL)

    print("[验证码] 在限定时间内未检测到目标")
    return False

def main():
    target_path = get_image_path()
    
    print("=" * 40)
    print(f"🤖 超级自动点击器 (拟人+防崩版)")
    print(f"📂 正在监听图片: {IMAGE_NAME}")
    print(f"🛑 停止运行请按 Ctrl+C")
    if SEARCH_REGION:
        print(f"🔍 已启用区域搜索优化: {SEARCH_REGION}")
    print("=" * 40)
    
    if not os.path.exists(target_path):
        print(f"❌ 错误：找不到文件 {target_path}")
        print("请确保图片和脚本在同一目录下。")
        return

    # --- 主循环结构优化 ---
    while True:
        try:
            # 1. 寻找图片
            # region 参数能极大降低内存占用，提升速度
            location = pyautogui.locateOnScreen(
                target_path, 
                confidence=CONFIDENCE, 
                grayscale=True,
                region=SEARCH_REGION
            )
            
            # 2. 如果找到（没报错且不为None），执行点击
            if location:
                simulate_human_click(location)
                print("⏳ 点击完成，冷却 3 秒...")
                time.sleep(random.uniform(2.5, 4.0))
            
        except pyautogui.ImageNotFoundException:
            # 找不到图片是常态，直接跳过进入下一次循环
            pass
            
        except Exception as e:
            # ⚠️ 捕获所有其他严重错误（如内存溢出、文件被占等）
            # 这里不会退出程序，而是打印错误并重试
            print(f"\n⚠️ 发生错误: {e}")
            print("🔄 程序未崩溃，将在 3 秒后尝试恢复...")
            time.sleep(3)
        
        # 每次扫描后的间隔
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 用户手动停止了程序。")
