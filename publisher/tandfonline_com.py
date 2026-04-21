from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext
import pyautogui

class TandfonlineComLoginHandler(PublisherLoginHandler):
    domain = "tandfonline.com"
    handler_name = "tandfonline_com"

    def login(self, domain: str, ctx: LoginContext) -> bool:
        ctx.log("[登录] 执行 tandfonline 登录流程")
        login_button_img = ctx.photo("tandfonline.com1.png")
        institution_input_img = ctx.photo("tandfonline.com2.png")
        select_institution_img = ctx.photo("tandfonline.com3.png")



        if not self._open_institution_login(login_button_img, ctx):
            return False
        return self._select_institution(institution_input_img, select_institution_img, ctx)
    
    @staticmethod
    def click_login_button(ctx: LoginContext) -> bool:
        pre_url = ctx.get_current_url()
        ctx.search_keyword("Access through your institution")
        ctx.sleep(0.5)
        ctx.press("esc", 1, 1)
        ctx.press("enter", 2, 1)
        ctx.sleep(2)
        current_url = ctx.get_current_url()
        return pre_url != current_url

    @staticmethod
    def _open_institution_login(login_button_img: str, ctx: LoginContext) -> bool:
        max_retries = 3
        for retry_count in range(1, max_retries + 1):
            ctx.log(f"[登录] 第 {retry_count}/{max_retries} 次尝试跳转机构登录页")
            if TandfonlineComLoginHandler.click_login_button(ctx):
                ctx.log("[登录] 已成功跳转到机构登录页")
                return True
            ctx.hotkey('refresh_page')
            ctx.sleep(20)

        ctx.log("[登陆] 跳转登陆页面失败")
        return False

    @staticmethod
    def _select_institution(
        institution_input_img: str,
        select_institution_img: str,
        ctx: LoginContext,
    ) -> bool:
        
        ctx.sleep(10)
        
        ctx.search_keyword('Type the name')
        ctx.press('tab',1,0.5)
        ctx.hotkey('shift_tab')

        ctx.log("[图像识别] 正在查找机构输入框...")
        # input_pos = ctx.locate_image(institution_input_img)
        # if not input_pos:
        #     ctx.log("[图像识别] 未找到机构输入框")
        #     return False

        # ctx.log(f"[图像识别] 找到机构输入框，位置: {input_pos}")
        # ctx.click(input_pos)
        # ctx.log("[登录] 已点击机构输入框")
        # ctx.sleep(20)
        ctx.log("[键盘输入] 输入机构名称: Zhejiang University")
        ctx.type_text("Zhejiang University", interval=0.1)
        ctx.sleep(3)
        ctx.press('down',1,0.2)
        ctx.press('enter',1,0.2)
        ctx.log("[页面跳转] 等待跳转到浙大登陆页")

        ctx.sleep(5)
        if ctx.is_zju_login_page():
            return ctx.zju_login()
        else:
            return True

        scroll_step = 300
        scroll_delay = 1
        max_scroll_attempts = 20
        ctx.log("[滚动页面] 开始滚动查找机构...")

        for attempt in range(max_scroll_attempts):
            select_pos = ctx.locate_image(select_institution_img)
            if select_pos:
                ctx.log(f"[图像识别] 找到机构选择按钮，位置: {select_pos}")
                ctx.click(select_pos)
                ctx.log("[登录] 已选择机构")
                ctx.sleep(10)
                ctx.press("enter")
                ctx.sleep(10)
                return True
            ctx.scroll(-scroll_step)
            ctx.sleep(scroll_delay)
            ctx.log(f"[滚动页面] 已滚动 {attempt + 1}/{max_scroll_attempts} 次...")

        ctx.log("[图像识别] 未找到机构选择按钮")
        return False


def get_handler() -> PublisherLoginHandler:
    return TandfonlineComLoginHandler()
