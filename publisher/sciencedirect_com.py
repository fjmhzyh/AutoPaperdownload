from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class ScienceDirectComLoginHandler(PublisherLoginHandler):
    domain = "sciencedirect.com"
    handler_name = "sciencedirect_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        # 已登陆或者开放获取，可以跳过登陆流程
        open_access,full_access,purchase_pdf = ctx.check_keywords_exist(["open access","full access","purchase pdf"])
        if purchase_pdf:
            return self.dispatch_login(ctx)
        if open_access or full_access :
            ctx.log("[免登陆检测]文章为open access, 无需登陆")
            return True
        else:
            return self.dispatch_login(ctx)

    def dispatch_login(self,ctx:LoginContext)->bool:
        login_button_image = ctx.photo("sciencedirect.com1.png")
        ctx.click(700, 1000)
        ctx.log("[图像识别] 正在查找登录按钮...")
        button_pos = ctx.locate_image(login_button_image)
        if not button_pos:
            ctx.log("[图像识别] 未找到登录按钮，尝试直接下载")
            return False

        ctx.log(f"[图像识别] 找到登录按钮，位置: {button_pos}")
        ctx.click(button_pos)
        ctx.log("[登录] 已点击登录按钮")
        ctx.sleep(10)
        ctx.press("enter")
        ctx.sleep(10)
        return True            


def get_handler() -> PublisherLoginHandler:
    return ScienceDirectComLoginHandler()
