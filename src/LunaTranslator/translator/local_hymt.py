"""Loopback-only preset using the existing Hy-MT2 prompt and Sakura transport."""

from translator.sakura_base import TS as SakuraTranslator
from language import Languages
from myutils.local_translation import local_args, local_server
from myutils.local_transport import LocalSession


class TS(SakuraTranslator):
    def hymt2_make_messages(self, contextnum, query, gpt_dict=None):
        messages = super().hymt2_make_messages(contextnum, query, gpt_dict)
        if not gpt_dict and self.tgtlang_1 in (Languages.Chinese, Languages.TradChinese):
            # The official card requires Chinese language names in Chinese
            # instructions. Keep this correction isolated from existing providers.
            messages[-1]["content"] = (
                "将以下文本翻译为{}，注意只需要输出翻译后的结果，不要额外解释：\n\n{}"
                .format(self.tgtlang_1.zhsname, query)
            )
        return messages

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
