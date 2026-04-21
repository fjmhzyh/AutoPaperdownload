from __future__ import annotations

from typing import Dict, Optional

from .advanced_onlinelibrary_wiley_com import get_handler as get_advanced_wiley_handler
from .analyticalsciencejournals_onlinelibrary_wiley_com import (
    get_handler as get_analytical_wiley_handler,
)
from .base import PublisherLoginHandler
from .ieeexplore_ieee_org import get_handler as get_ieee_handler
from .iopscience_iop_org import get_handler as get_iop_handler
from .karger_com import get_handler as get_karger_handler
from .link_springer_com import get_handler as get_springer_handler
from .onlinelibrary_wiley_com import get_handler as get_wiley_handler
from .pubs_acs_org import get_handler as get_acs_handler
from .pubs_rsc_org import get_handler as get_rsc_handler
from .registry import normalize_domain
from .sciencedirect_com import get_handler as get_sciencedirect_handler
from .tandfonline_com import get_handler as get_tandf_handler


class LegacyLoginFallback:
    """旧登录逻辑兜底（保持域名兼容和不中断特性）"""

    def __init__(self):
        self._exact_map: Dict[str, PublisherLoginHandler] = {
            "pubs.acs.org": get_acs_handler(),
            "sciencedirect.com": get_sciencedirect_handler(),
            "link.springer.com": get_springer_handler(),
            "tandfonline.com": get_tandf_handler(),
            "advanced.onlinelibrary.wiley.com": get_advanced_wiley_handler(),
            "onlinelibrary.wiley.com": get_wiley_handler(),
            "analyticalsciencejournals.onlinelibrary.wiley.com": get_analytical_wiley_handler(),
            "iopscience.iop.org": get_iop_handler(),
            "ieeexplore.ieee.org": get_ieee_handler(),
            "karger.com": get_karger_handler(),
            "pubs.rsc.org": get_rsc_handler(),
        }
        self._suffix_map: Dict[str, PublisherLoginHandler] = {
            "acs.org": get_acs_handler(),
            "springer.com": get_springer_handler(),
            "wiley.com": get_wiley_handler(),
            "sciencedirect.com": get_sciencedirect_handler(),
            "tandfonline.com": get_tandf_handler(),
            "iop.org": get_iop_handler(),
            "ieee.org": get_ieee_handler(),
            "karger.com": get_karger_handler(),
            "rsc.org": get_rsc_handler(),
        }

    def _resolve_legacy_handler(self, domain: str) -> Optional[PublisherLoginHandler]:
        normalized = normalize_domain(domain)
        if not normalized:
            return None

        exact = self._exact_map.get(normalized)
        if exact:
            return exact

        for suffix, handler in self._suffix_map.items():
            if normalized == suffix or normalized.endswith(f".{suffix}"):
                return handler
        return None

    def perform_login(self, domain: str, ctx) -> bool:
        normalized = normalize_domain(domain)
        handler = self._resolve_legacy_handler(normalized)
        if not handler:
            ctx.log(f"[登录兜底] 无legacy处理器: domain={normalized}")
            return False

        try:
            ctx.log(f"[登录兜底] 使用legacy逻辑: domain={normalized} handler={handler.handler_name}")
            return bool(handler.login(normalized, ctx))
        except Exception as e:
            ctx.log(f"[登录兜底] legacy执行异常: domain={normalized} error={e}")
            return False
