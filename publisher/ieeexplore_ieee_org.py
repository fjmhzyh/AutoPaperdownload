from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class IeeexploreIeeeOrgLoginHandler(PublisherLoginHandler):
    domain = "ieeexplore.ieee.org"
    handler_name = "ieeexplore_ieee_org"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行IEEE Xplore登录流程")
        login_button_img = ctx.photo("ieeexplore.ieee.org1.png")
        submit_button_img = ctx.photo("ieeexplore.ieee.org2.png")

        clicked_first = False
        ctx.log("[图像识别] 正在查找登录按钮1...")
        button_pos = ctx.locate_image(login_button_img)
        if button_pos:
            ctx.log("[图像识别] 找到登录按钮1")
            ctx.click(button_pos)
            ctx.log("[登录] 已点击登录按钮1")
            ctx.sleep(20)
            clicked_first = True
        else:
            ctx.log("[图像识别] 未找到登录按钮1，尝试直接下载")

        clicked_second = False
        ctx.log("[图像识别] 正在查找登录按钮2...")
        button_pos = ctx.locate_image(submit_button_img)
        if button_pos:
            ctx.log("[图像识别] 找到登录按钮2")
            ctx.click(button_pos)
            ctx.log("[登录] 已点击登录按钮2")
            ctx.sleep(10)
            ctx.press("enter")
            ctx.sleep(10)
            clicked_second = True
        else:
            ctx.log("[图像识别] 未找到登录按钮2")

        return clicked_first or clicked_second


def get_handler() -> PublisherLoginHandler:
    return IeeexploreIeeeOrgLoginHandler()
