from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class KargerComLoginHandler(PublisherLoginHandler):
    domain = "karger.com"
    handler_name = "karger_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行Karger登录流程")
        login_button_img = ctx.photo("karger.com1.png")
        submit_button_img = ctx.photo("karger.com2.png")

        button_pos = ctx.locate_image(login_button_img)
        if not button_pos:
            scroll_step = 900
            scroll_delay = 1
            max_scroll_attempts = 60
            ctx.log("[滚动检测] 开始滚动查找登录按钮...")
            for attempt in range(max_scroll_attempts):
                ctx.scroll(-scroll_step)
                ctx.sleep(scroll_delay)
                button_pos = ctx.locate_image(login_button_img)
                if button_pos:
                    break
                ctx.log(f"[滚动检测] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

        if button_pos:
            ctx.log("[图像识别] 找到登录按钮1")
            ctx.click(button_pos)
            ctx.log("[登录] 已点击登录按钮1")
            ctx.sleep(5)
        else:
            ctx.log("[图像识别] 未找到登录按钮1")
            return False

        ctx.log("[图像识别] 正在查找登录按钮2...")
        button_pos = ctx.locate_image(submit_button_img)
        if not button_pos:
            ctx.log("[图像识别] 未找到登录按钮2")
            return False

        ctx.log("[图像识别] 找到登录按钮2")
        ctx.click(button_pos)
        ctx.log("[登录] 已点击登录按钮2")
        ctx.sleep(5)
        ctx.press("enter")
        ctx.sleep(10)
        return True


def get_handler() -> PublisherLoginHandler:
    return KargerComLoginHandler()
