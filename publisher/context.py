from __future__ import annotations

import os
import time
from typing import List, Optional, Tuple

import pyautogui
import pyperclip

from image_resolver import get_profile_info, log_profile_once, resolve_image_path
from platform_compat import hotkey as platform_hotkey
from platform_compat import is_mac
from runtime_config import load_runtime_config


class LoginContext:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir
        log_profile_once(logger=self.log, base_dir=self.base_dir)

    def photo(self, filename: str) -> str:
        resolved = resolve_image_path(
            filename,
            base_dir=self.base_dir,
            logger=self.log,
        )
        if resolved:
            return resolved
        info = get_profile_info(self.base_dir)
        return os.path.join(info["profile_path"], filename)

    def log(self, message: str) -> None:
        print(message)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def hotkey(self, action_name: str) -> None:
        platform_hotkey(action_name)

    def press(self, key: str, presses: int = 1, interval: float = 0.0) -> None:
        pyautogui.press(key, presses=presses, interval=interval)

    def type_text(self, text: str, interval: float = 0.1) -> None:
        pyautogui.write(text, interval=interval)

    def scroll(self, amount: int) -> None:
        pyautogui.scroll(amount)

    def get_current_url(self):
        pyperclip.copy('')
        self.log('开始获取当前地址')
        platform_hotkey("focus_address_bar")
        time.sleep(1)
        platform_hotkey("select_all")
        time.sleep(1)
        platform_hotkey("copy")
        time.sleep(2)
        pyautogui.press('esc')
        # 获取URL
        url = pyperclip.paste()
        # 取消选中
        return url

    def is_zju_login_page(self, url: Optional[str] = None) -> bool:
        """
        判断当前URL（或传入URL）是否为浙大统一认证相关页面。
        """
        # pyautogui.press("tab",presses=3,interval=0.2)
        current_url = self.get_current_url().strip()
        # current_url = self.get_url_manual()
        result = "zjuam.zju.edu.cn" in current_url.lower() or current_url==""
        self.log(f"当前url:{current_url}")
        self.log(f"是否是浙大登陆页:{result}")
        return result

    def zju_login(self) -> bool:
        """
        从运行配置读取浙大账号密码，自动填充并点击登录按钮。
        配置键支持:
        - zju_username / zju_password
        - params.zju_username / params.zju_password
        """
        cfg = load_runtime_config()
        params = cfg.get("params", {}) if isinstance(cfg, dict) else {}

        self.log(f"[浙大登陆]开始执行浙大登陆逻辑")

        username = ""
        password = ""
        if isinstance(cfg, dict):
            username = str(cfg.get("zju_username", "")).strip()
            password = str(cfg.get("zju_password", "")).strip()
        if not username:
            username = str(params.get("zju_username", "")).strip()
        if not password:
            password = str(params.get("zju_password", "")).strip()

        if not username or not password:
            self.log("[浙大登录] 未找到 zju_username / zju_password，已跳过自动登录")
            return False

        self.log("[浙大登录] 开始自动填写账号密码")
        try:
            # 默认当前焦点在用户名输入框；逐字段覆盖输入
            self.press("tab", presses=1, interval=0.1)
            self.hotkey("select_all")
            self.type_text(username, interval=0.05)
            self.press("tab", presses=1, interval=0.1)
            self.hotkey("select_all")
            self.type_text(password, interval=0.05)
        except Exception as exc:
            self.log(f"[浙大登录] 输入账号密码失败: {exc}")
            return False

        btn_pos = self.locate_image("zju.login.png", confidence=0.8, retry=3, retry_interval=1.0)
        if not btn_pos:
            self.log("[浙大登录] 未定位到登录按钮图片: zju.login.png")
            return False

        self.click_image(btn_pos)
        self.log("[浙大登录] 已点击登录按钮，等待10秒...")
        self.sleep(10)
        result = self.is_zju_login_page()
        if result:
            self.log(f"[浙大登陆]登陆失败")
        return not result

    def search_keyword_and_clear(self, keyword)->None:
        modifykey = 'command' if is_mac() else 'ctrl'
        pyautogui.hotkey(modifykey, 'f')
        time.sleep(1) 
        # 3. 输入搜索内容
        pyautogui.typewrite(keyword, interval=0.1)
        time.sleep(1)  # 稍微等待，让浏览器完成查找高亮
        # 4. 按下 ESC 键关闭查找框
        pyautogui.press('backspace',presses=len(keyword), interval=0.1)
        pyautogui.press('esc')
    def search_keyword(self, keyword)->None:
        modifykey = 'command' if is_mac() else 'ctrl'
        pyautogui.hotkey(modifykey, 'f')
        time.sleep(1) 
        # 3. 输入搜索内容
        pyautogui.typewrite(keyword, interval=0.1)
        time.sleep(1)  # 稍微等待，让浏览器完成查找高亮
        # 4. 按下 ESC 键关闭查找框
        pyautogui.press('esc')

    def check_keyword_exist(self, keyword: str) -> bool:
        """
        全选当前网页内容并复制，判断是否包含指定关键字。
        包含返回 True，不包含返回 False。
        """
        target = (keyword or "").strip()
        if not target:
            self.log("[关键词检查] 关键字为空，返回False")
            return False

        try:
            # 先点击页面中部，尽量把焦点放到网页内容区域
            # screen_w, screen_h = pyautogui.size()
            # pyautogui.click(50, screen_h // 2)
            # self.sleep(0.2)

            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                old_clipboard = ""

            pyperclip.copy("")
            self.hotkey("select_all")
            self.sleep(0.2)
            self.hotkey("copy")
            self.sleep(1)

            content = (pyperclip.paste() or "")
            result = target.lower() in content.lower()
            self.log(
                f"[关键词检查] keyword={target} 内容长度={len(content)} 结果={result}"
            )

            # 尽量恢复原剪贴板，避免影响其他流程
            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass

            # 恢复页面到没选中的状态
            self.search_keyword('1')
            return result
        except Exception as exc:
            self.log(f"[关键词检查] 检查失败: {exc}")
            return False

    def check_keywords_exist(self, keywords: List[str]) -> Tuple[bool, ...]:
        """
        批量检查多个关键字是否存在于当前网页文本中，按传入顺序返回布尔元组。
        例如:
        a, b, c = ctx.check_keywords_exist(["hello", "roke", "abc"])
        """
        cleaned_keywords = []
        for item in keywords or []:
            key = str(item or "").strip()
            if key:
                cleaned_keywords.append(key)

        if not cleaned_keywords:
            self.log("[关键词批量检查] 关键字列表为空，返回空元组")
            return tuple()

        results = [False] * len(cleaned_keywords)
        try:
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                old_clipboard = ""

            pyperclip.copy("")
            self.hotkey("select_all")
            self.sleep(0.2)
            self.hotkey("copy")
            self.sleep(1)

            content = (pyperclip.paste() or "")
            content_lower = content.lower()

            for idx, key in enumerate(cleaned_keywords):
                results[idx] = key.lower() in content_lower

            summary = ", ".join([f"{k}={results[i]}" for i, k in enumerate(cleaned_keywords)])
            self.log(
                f"[关键词批量检查] 内容长度={len(content)} 结果: {summary}"
            )

            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass

            self.cancel_select_all()
            return tuple(results)
        except Exception as exc:
            self.log(f"[关键词批量检查] 检查失败: {exc}")
            return tuple(results)

    def cancel_select_all(self):
        platform_hotkey('search')
        time.sleep(1) 
        # 3. 输入搜索内容
        pyautogui.typewrite(' ', interval=0.1)
        time.sleep(1)  # 稍微等待，让浏览器完成查找高亮
        pyautogui.press('enter',2,0.5)
        # 4. 按下 ESC 键关闭查找框
        pyautogui.press('esc')

    def click(self, target, y: Optional[int] = None) -> None:
        if y is None:
            x, y_pos = target
            pyautogui.click(x, y_pos)
        else:
            pyautogui.click(int(target), int(y))

    def click_image(self, position: Tuple[int, int]) -> None:
        x, y = position
        pyautogui.moveTo(x, y, duration=0.5)
        pyautogui.click()
        self.log(f"[鼠标操作] 已点击位置: ({x}, {y})")

    def locate_image_on_screen(self, image_path: str, confidence: float = 0.9) -> Optional[Tuple[int, int]]:
        try:
            if not os.path.exists(image_path):
                self.log(f"[图像识别警告] 图像文件不存在: {image_path}")
                return None

            location = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if location:
                center_x = location.left + location.width // 2
                center_y = location.top + location.height // 2
                if is_mac():
                    center_x //= 2
                    center_y //= 2
                return (center_x, center_y)
            return None
        except Exception:
            return None

    def _resolve_image_path(self, image_name_or_path: str) -> str:
        if os.path.isabs(image_name_or_path):
            return image_name_or_path
        if os.path.dirname(image_name_or_path):
            return image_name_or_path
        return self.photo(image_name_or_path)

    def locate_image(
        self,
        image_name_or_path: str,
        confidence: float = 0.8,
        retry: int = 3,
        retry_interval: float = 1.0,
        scroll: bool = False,
        max_scrolls: int = 5,
        scroll_step: int = 900,
    ) -> Optional[Tuple[int, int]]:
        image_path = self._resolve_image_path(image_name_or_path)
        self.log(f"图片路径：{image_path}")
        attempts = max(retry, 1)
        for attempt in range(attempts):
            pos = self.locate_image_on_screen(image_path, confidence=confidence)
            if pos:
                return pos
            if scroll:
                if self.scroll_until_image_found(
                    image_path,
                    max_scrolls=max_scrolls,
                    scroll_step=scroll_step,
                    scroll_delay=retry_interval,
                ):
                    return self.locate_image_on_screen(image_path, confidence=confidence)
            if attempt < attempts - 1:
                self.sleep(retry_interval)
        return None

    def scroll_until_image_found(
        self,
        image_path: str,
        max_scrolls: int = 5,
        scroll_step: int = 900,
        scroll_delay: float = 1.0,
    ) -> bool:
        for attempt in range(max_scrolls):
            pos = self.locate_image_on_screen(image_path)
            if pos:
                self.click_image(pos)
                return True
            self.scroll(-scroll_step)
            self.sleep(scroll_delay)
            self.log(f"[滚动检测] 已滚动 {attempt + 1}/{max_scrolls} 次...")
        return False

    def enhanced_locate_image(self, image_path: str, scroll_retry: bool = True) -> Optional[Tuple[int, int]]:
        pos = self.locate_image_on_screen(image_path)
        if pos:
            return pos

        if scroll_retry:
            self.log("[图像识别] 初始查找失败，尝试滚动页面...")
            if self.scroll_until_image_found(image_path):
                return self.locate_image_on_screen(image_path)
        return None
