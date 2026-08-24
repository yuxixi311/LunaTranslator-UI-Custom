class TranslateResult:
    def __init__(self, id=None, result=None):
        self.id = id
        self.result = result

    def __bool__(self):
        return bool(self.result)


class TranslateError:

    def __init__(self, id=None, message=None):
        self.id = id
        self.message = message

    def __bool__(self):
        return bool(self.message)


class WordSegResult:
    def __init__(
        self,
        word,
        kana: str = None,
        isdeli=False,
        wordclass: str = None,
        prototype: str = None,
        donthighlight=False,
        hidekana=False,
        info=None,
        isshit=False,
        specialinfo=None,
        grammar_role=None,
        grammar_dep=None,
        grammar_head=None,
        bunsetu_id=None,
        bunsetu_text=None,
        bunsetu_start=False,
        bunsetu_end=False,
        learning_unit_id=None,
        learning_unit_text=None,
        learning_unit_start=False,
        learning_unit_end=False,
        **_
    ):
        self.donthighlight = donthighlight
        self.word = word
        self.kana = kana
        self.isdeli = isdeli
        self.wordclass = wordclass
        self._prototype = prototype
        self.hidekana = hidekana
        self.info = info
        self.specialinfo = specialinfo
        self.isshit = isshit
        self.grammar_role = grammar_role
        self.grammar_dep = grammar_dep
        self.grammar_head = grammar_head
        self.bunsetu_id = bunsetu_id
        self.bunsetu_text = bunsetu_text
        self.bunsetu_start = bunsetu_start
        self.bunsetu_end = bunsetu_end
        self.learning_unit_id = learning_unit_id
        self.learning_unit_text = learning_unit_text
        self.learning_unit_start = learning_unit_start
        self.learning_unit_end = learning_unit_end

    @property
    def prototype(self):
        if self._prototype:
            return self._prototype
        return self.word

    def as_dict(self):
        return dict(
            word=self.word,
            kana=self.kana,
            isdeli=self.isdeli,
            wordclass=self.wordclass,
            prototype=self._prototype,
            hidekana=self.hidekana,
            info=self.info,
            isshit=self.isshit,
            specialinfo=self.specialinfo,
            donthighlight=self.donthighlight,
            grammar_role=self.grammar_role,
            grammar_dep=self.grammar_dep,
            grammar_head=self.grammar_head,
            bunsetu_id=self.bunsetu_id,
            bunsetu_text=self.bunsetu_text,
            bunsetu_start=self.bunsetu_start,
            bunsetu_end=self.bunsetu_end,
            learning_unit_id=self.learning_unit_id,
            learning_unit_text=self.learning_unit_text,
            learning_unit_start=self.learning_unit_start,
            learning_unit_end=self.learning_unit_end,
        )

    def __str__(self):
        return str(self.as_dict())

    def __repr__(self):
        return str(self)

    @staticmethod
    def from_dict(d: dict):
        return WordSegResult(
            d["word"],
            d.get("kana"),
            d.get("isdeli", False),
            d.get("wordclass"),
            d.get("prototype"),
            info=d.get("info"),
            isshit=d.get("isshit", False),
            specialinfo=d.get("specialinfo"),
            donthighlight=d.get("donthighlight"),
            grammar_role=d.get("grammar_role"),
            grammar_dep=d.get("grammar_dep"),
            grammar_head=d.get("grammar_head"),
            bunsetu_id=d.get("bunsetu_id"),
            bunsetu_text=d.get("bunsetu_text"),
            bunsetu_start=d.get("bunsetu_start", False),
            bunsetu_end=d.get("bunsetu_end", False),
            learning_unit_id=d.get("learning_unit_id"),
            learning_unit_text=d.get("learning_unit_text"),
            learning_unit_start=d.get("learning_unit_start", False),
            learning_unit_end=d.get("learning_unit_end", False),
        )
