from __future__ import annotations

from abc import ABC, abstractmethod

from .context import LoginContext


class PublisherLoginHandler(ABC):
    domain: str = ""
    handler_name: str = ""

    def supports(self, domain: str) -> bool:
        check = (domain or "").strip().lower()
        return bool(self.domain) and check == self.domain

    @abstractmethod
    def login(self, domain: str, ctx: LoginContext) -> bool:
        raise NotImplementedError

