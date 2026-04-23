from __future__ import annotations

from .base import PublisherLoginHandler
from .context import LoginContext


class PubsAcsOrgLoginHandler(PublisherLoginHandler):
    domain = "pubs.acs.org"
    handler_name = "pubs_acs_org"

    def login(self, domain: str, ctx: LoginContext) -> bool:

        access_through, zhejiang_university,open_pdf = ctx.check_keywords_exist(['access through', 'zhejiang uniersity', 'open pdf'])

        # 之前登陆过，直接登陆浙大登陆页，按enter实现登陆
        if access_through and zhejiang_university:
            click_result = self.click_login_btn(ctx)
            if click_result:
                ctx.sleep(15)
                # 进入浙大登陆页，按enter键登陆
                ctx.press("enter")
                ctx.sleep(10)
                return True
            else:
                return False

        # 之前没有登陆过，执行整套登陆逻辑
        if access_through and not open_pdf:
            click_result = self.click_login_btn(ctx)
            if click_result:
                ctx.sleep(30)
                ctx.search_keyword('Search By University')
                # 聚焦到输入框，并输入浙大
                ctx.press('tab')
                ctx.hotkey('shift_tab')
                ctx.type_text("Zhejiang University", interval=0.1)
                ctx.sleep(3)
                #选中浙大并点击
                ctx.press('down',1,0.2)
                ctx.press('enter',1,0.2)
                ctx.log("[页面跳转] 等待跳转到浙大登陆页")

                ctx.sleep(15)
                ctx.press('enter')
                ctx.sleep(20)
                return True
            else:
                return False
        else:
            ctx.log(f"[免登录检测]当前文章无需登陆")
            return True

    def click_login_btn(self, ctx: LoginContext) -> bool:
        login_button_image = ctx.photo("pubs.acs.org1.png") 
        ctx.log("[图像识别] 正在查找登录按钮...")
        button_pos = ctx.locate_image(login_button_image)
        if not button_pos:
            ctx.log("[图像识别] 未找到登录按钮，尝试查找关键字登陆")
            ctx.search_keyword('access through')
            ctx.sleep(0.5)
            ctx.press("esc", 1, 1)
            ctx.press("enter", 2, 1)
            return True

        ctx.log(f"[图像识别] 找到登录按钮，位置: {button_pos}")
        ctx.click(button_pos)
        return True
    
def get_handler() -> PublisherLoginHandler:
    return PubsAcsOrgLoginHandler()
