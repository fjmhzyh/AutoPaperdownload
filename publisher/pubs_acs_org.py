from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class PubsAcsOrgLoginHandler(PublisherLoginHandler):
    domain = "pubs.acs.org"
    handler_name = "pubs_acs_org"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        access_through = ctx.check_keyword_exist('access through')
        open_pdf = ctx.check_keyword_exist('open pdf')
        if access_through and not open_pdf:
            login_button_image = ctx.photo("pubs.acs.org1.png")
            ctx.log("[图像识别] 正在查找登录按钮...")
            button_pos = ctx.locate_image(login_button_image)
            if not button_pos:
                ctx.log("[图像识别] 未找到登录按钮，尝试直接下载")
                return False

            ctx.log(f"[图像识别] 找到登录按钮，位置: {button_pos}")
            ctx.click(button_pos)
            ctx.log("[登录] 已点击登录按钮")
            ctx.sleep(10)
            # 进入浙大登陆页，按enter键登陆
            ctx.press("enter")
            ctx.sleep(10)
            return True
        else:
            ctx.log(f"[免登录检测]当前文章无需登陆")
            return True


def get_handler() -> PublisherLoginHandler:
    return PubsAcsOrgLoginHandler()
