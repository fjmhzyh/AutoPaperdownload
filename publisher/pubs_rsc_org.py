from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext
import time

class PubsRscOrgLoginHandler(PublisherLoginHandler):
    domain = "pubs.rsc.org"
    handler_name = "pubs_rsc_org"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        open_access,access_provided_by= ctx.check_keywords_exist(['This article is Open Access','access provided by'])
        if open_access or access_provided_by:
            ctx.log(f'[免登陆检测]当前文章为open aceess，无需登陆')
            return True
        else:
            ctx.log("[登录] 执行RSC Publications登录流程")
            login_button_img = ctx.photo("pubs.rsc.org1.png")
            submit_button_img = ctx.photo("pubs.rsc.org2.png")
            final_button_img = ctx.photo("pubs.rsc.org3.png")

            ctx.log("[图像识别] 正在查找登录按钮1...")
            first_pos = ctx.locate_image(login_button_img)
            if not first_pos:
                ctx.log("[图像识别] 未找到登录按钮1，尝试直接下载")
                return False
            ctx.log("[图像识别] 找到登录按钮1")
            ctx.click(first_pos)
            ctx.log("[登录] 已点击登录按钮1")
            ctx.sleep(30)

            ctx.log("[图像识别] 正在查找登录按钮2...")
            second_pos = ctx.locate_image(submit_button_img)
            if not second_pos:
                ctx.log("[图像识别] 未找到登录按钮2")
                return False
            ctx.log("[图像识别] 找到登录按钮2")
            ctx.click(second_pos)
            ctx.log("[登录] 已点击登录按钮2")
            ctx.sleep(5)

            ctx.search_keyword("zhejiang")
            ctx.sleep(2)
            third_pos = ctx.locate_image(final_button_img,0.9)
            if third_pos:
                ctx.log("[图像识别] 找到登录按钮3")
                ctx.click(third_pos)
                ctx.log("[登录] 已点击登录按钮3")
                ctx.sleep(15)
                ctx.press("enter")
                ctx.sleep(5)
                return True
            # scroll_step = 900
            # scroll_delay = 1
            # max_scroll_attempts = 120
            # ctx.log("[滚动检测] 开始滚动查找登录按钮3...")
            # for attempt in range(max_scroll_attempts):
            #     ctx.scroll(-scroll_step)
            #     ctx.sleep(scroll_delay)
            #     third_pos = ctx.locate_image(final_button_img)
            #     if third_pos:
            #         ctx.log("[图像识别] 找到登录按钮3")
            #         ctx.click(third_pos)
            #         ctx.log("[登录] 已点击登录按钮3")
            #         ctx.sleep(5)
            #         return True
            #     ctx.log(f"[滚动检测] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

            # ctx.log("[图像识别] 未找到登录按钮3")
            return False


def get_handler() -> PublisherLoginHandler:
    return PubsRscOrgLoginHandler()
