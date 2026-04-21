from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class AdvancedOnlinelibraryWileyComLoginHandler(PublisherLoginHandler):
    domain = "advanced.onlinelibrary.wiley.com"
    handler_name = "advanced_onlinelibrary_wiley_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行advanced_onlinelibaray_wiley登录流程")
        login_button_img = ctx.photo("advanced.onlinelibrary.wiley.com1.png")
        submit_button_img = ctx.photo("advanced.onlinelibrary.wiley.com2.png")
        # 检查文章是否开源，开源则跳过登陆流程
        check_result =ctx.check_keyword_exist("open access")
        if check_result:
            ctx.log("[开源检测]文章为open access, 无需登陆")
            return True
        else:
            return _run_wiley_two_step_flow(ctx, login_button_img, submit_button_img)


def _run_wiley_two_step_flow(ctx: LoginContext, login_button_img: str, submit_button_img: str) -> bool:
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


    # 小屏幕看不到，需往下拉一点
    ctx.press('down',5,0.2);

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
    return AdvancedOnlinelibraryWileyComLoginHandler()
