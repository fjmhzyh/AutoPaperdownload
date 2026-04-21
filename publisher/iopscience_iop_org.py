from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class IopscienceIopOrgLoginHandler(PublisherLoginHandler):
    domain = "iopscience.iop.org"
    handler_name = "iopscience_iop_org"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行IOP Science登录流程")
        login_button_img = ctx.photo("iopscience.iop.org1.png")
        first_button_img = ctx.photo("iopscience.iop.org2.png")

        first_pos = ctx.locate_image(first_button_img)
        if first_pos:
            ctx.log("[图像识别] 找到登录按钮1")
            ctx.click(first_pos)
            ctx.log("[登录] 已点击登录按钮1")
            ctx.sleep(20)
        else:
            ctx.log("[图像识别] 未找到登录按钮1，尝试继续查找按钮2")

        scroll_step = 300
        scroll_delay = 1
        max_scroll_attempts = 60
        ctx.log("[滚动检测] 开始滚动查找登录按钮...")

        for attempt in range(max_scroll_attempts):
            ctx.scroll(-scroll_step)
            ctx.sleep(scroll_delay)
            button_pos = ctx.locate_image(login_button_img)
            if button_pos:
                ctx.log("[图像识别] 找到登录按钮2")
                ctx.click(button_pos)
                ctx.log("[登录] 已点击登录按钮2")
                ctx.sleep(10)
                ctx.press("enter")
                ctx.sleep(20)
                return True
            ctx.log(f"[滚动检测] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

        ctx.log("[滚动检测] 达到最大滚动次数仍未找到按钮")
        return False


def get_handler() -> PublisherLoginHandler:
    return IopscienceIopOrgLoginHandler()
