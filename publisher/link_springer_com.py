from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class LinkSpringerComLoginHandler(PublisherLoginHandler):
    domain = "link.springer.com"
    handler_name = "link_springer_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行Springer登录流程")
        login_button_img = ctx.photo("link.springer.com1.png")
        institution_input_img = ctx.photo("link.springer.com3.png")
        select_institution_img = ctx.photo("link.springer.com2.png")

        if not self._open_institution_login(login_button_img, ctx):
            return False
        return self._select_institution(institution_input_img, select_institution_img, ctx)

    @staticmethod
    def _open_institution_login(login_button_img: str, ctx: LoginContext) -> bool:

        ctx.search_keyword('log in via')
        ctx.sleep(1)

        scroll_step = 900
        scroll_delay = 1
        max_scroll_attempts = 60

        button_pos = ctx.locate_image(login_button_img)
        if button_pos:
            ctx.log("[图像识别] 找到登录按钮1")
            ctx.click(button_pos)
            ctx.log("[登录] 已点击登录按钮1")
            ctx.sleep(5)
            return True

        # ctx.log("[滚动检测] 开始滚动查找登录按钮...")
        # for attempt in range(max_scroll_attempts):
        #     ctx.scroll(-scroll_step)
        #     ctx.sleep(scroll_delay)
        #     button_pos = ctx.locate_image(login_button_img)
        #     if button_pos:
        #         ctx.log("[图像识别] 找到登录按钮1")
        #         ctx.click(button_pos)
        #         ctx.log("[登录] 已点击登录按钮1")
        #         ctx.sleep(5)
        #         return True
        #     ctx.log(f"[滚动检测] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

        # ctx.log("[图像识别] 未找到登录按钮1")
        return False

    @staticmethod
    def _select_institution(
        institution_input_img: str,
        select_institution_img: str,
        ctx: LoginContext,
    ) -> bool:
        ctx.log("[图像识别] 正在查找机构输入框...")
        input_pos = ctx.locate_image(institution_input_img)
        if not input_pos:
            ctx.log("[图像识别] 未找到机构输入框")
            return False

        ctx.log(f"[图像识别] 找到机构输入框，位置: {input_pos}")
        ctx.click(input_pos)
        ctx.log("[登录] 已点击机构输入框")
        ctx.sleep(20)
        ctx.log("[键盘输入] 输入机构名称: Zhejiang University")
        ctx.type_text("Zhejiang University", interval=0.1)
        ctx.sleep(1)
        ctx.press('down', 9, 0.1)
        ctx.press('enter', 1, 0.2)

        # scroll_step = 300
        # scroll_delay = 1
        # max_scroll_attempts = 20
        # ctx.log("[滚动页面] 开始滚动查找机构...")

        # for attempt in range(max_scroll_attempts):
        #     select_pos = ctx.locate_image(select_institution_img)
        #     if select_pos:
        #         ctx.log(f"[图像识别] 找到机构选择按钮，位置: {select_pos}")
        #         ctx.click(select_pos)
        #         ctx.log("[登录] 已选择机构")
        #         ctx.sleep(10)
        #         ctx.press("enter")
        #         ctx.sleep(10)
        #         return True
        #     ctx.scroll(-scroll_step)
        #     ctx.sleep(scroll_delay)
        #     ctx.log(f"[滚动页面] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

        # ctx.log("[图像识别] 未找到机构选择按钮")
        # return False


def get_handler() -> PublisherLoginHandler:
    return LinkSpringerComLoginHandler()
