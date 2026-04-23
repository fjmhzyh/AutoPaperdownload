from __future__ import annotations

from .advanced_onlinelibrary_wiley_com import _run_wiley_two_step_flow
from .base import PublisherLoginHandler
from .context import LoginContext


class AnalyticalWileyComLoginHandler(PublisherLoginHandler):
    domain = "analyticalsciencejournals.onlinelibrary.wiley.com"
    handler_name = "analyticalsciencejournals_onlinelibrary_wiley_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行Wiley Analytical Science Journals登录流程")
        login_button_img = ctx.photo("advanced.onlinelibrary.wiley.com1.png")
        submit_button_img = ctx.photo("advanced.onlinelibrary.wiley.com2.png")
                # 检查文章是否开源，开源则跳过登陆流程
        open_access,full_access = ctx.check_keywords_exist(["open access","full access"])
        if open_access or full_access:
            ctx.log("[开源检测]文章为open access, 无需登陆")
            return True
        else:
            return _run_wiley_two_step_flow(ctx, login_button_img, submit_button_img)


def get_handler() -> PublisherLoginHandler:
    return AnalyticalWileyComLoginHandler()
