import pyautogui

# 步骤1：把鼠标移到目标图标上，运行这行获取坐标
print(pyautogui.position())

# 步骤2：根据坐标截取图标（例如坐标是 500, 300，图标大小约 40x40）
# 注意：区域要稍微大一点，包含完整图标
srceenshot = pyautogui.screenshot('rss_icon_mac.png', region=(500, 300, 60, 60))
srceenshot.save('rss_icon_mac.png');

# 步骤3：用新截图去匹配
pos = pyautogui.locateOnScreen('rss_icon_mac.png', confidence=0.7)