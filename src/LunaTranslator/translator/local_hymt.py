"""Loopback-only preset using the existing Hy-MT2 prompt and Sakura transport."""

from translator.sakura_base import TS as SakuraTranslator
from myutils.local_translation import local_args, local_server
from myutils.local_transport import LocalSession


class TS(SakuraTranslator):
    @property
    def config(self):
        port, alias = local_server.require_ready()
        return local_args(super().config, port, alias)

    @property
    def proxy(self):
        return {"http": None, "https": None}

    def result_cache_key(self, src, tgt, sentence):
        # Never reuse a translation from a different model/server session.
        _, alias = local_server.require_ready()
        return super().result_cache_key(src, tgt, sentence) + (alias, "Hy-MT2")

    def translate(self, query):
        try:
            yield from super().translate(query)
        finally:
            self.proxysession.close_response()
            # Bound retained history even when context is disabled for a long game.
            self.context = self.context[-6:]
            self.contextReal = self.contextReal[-6:]

    def renewsesion(self):
        self.proxysession = LocalSession()
