from __future__ import annotations

from typing import Dict, Optional
from urllib.parse import urlparse

from .advanced_onlinelibrary_wiley_com import get_handler as get_advanced_wiley_handler
from .aiche_onlinelibrary_wiley_com import get_handler as get_aiche_wiley_handler
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
from .sciencedirect_com import get_handler as get_sciencedirect_handler
from .tandfonline_com import get_handler as get_tandf_handler


def normalize_domain(domain: str) -> str:
    raw = (domain or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = (urlparse(raw).netloc or "").strip().lower()
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw


_HANDLER_FACTORIES = {
    "pubs.acs.org": get_acs_handler,
    "link.springer.com": get_springer_handler,
    "advanced.onlinelibrary.wiley.com": get_advanced_wiley_handler,
    "onlinelibrary.wiley.com": get_wiley_handler,
    "analyticalsciencejournals.onlinelibrary.wiley.com": get_analytical_wiley_handler,
    "aiche.onlinelibrary.wiley.com": get_aiche_wiley_handler,
    "sciencedirect.com": get_sciencedirect_handler,
    "tandfonline.com": get_tandf_handler,
    "iopscience.iop.org": get_iop_handler,
    "ieeexplore.ieee.org": get_ieee_handler,
    "karger.com": get_karger_handler,
    "pubs.rsc.org": get_rsc_handler,
    "chemistry-europe.onlinelibrary.wiley.com":get_advanced_wiley_handler
}

_HANDLER_MAP: Dict[str, PublisherLoginHandler] = {
    domain: factory() for domain, factory in _HANDLER_FACTORIES.items()
}


def resolve_handler(domain: str) -> Optional[PublisherLoginHandler]:
    normalized = normalize_domain(domain)
    if not normalized:
        return None

    handler = _HANDLER_MAP.get(normalized)
    if handler:
        return handler

    parts = normalized.split(".")
    if len(parts) >= 2:
        main_domain = ".".join(parts[-2:])
        return _HANDLER_MAP.get(main_domain)
    return None

