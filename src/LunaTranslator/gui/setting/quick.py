"""
LunaTranslator Learning UI - 常用设置 (frequently used settings aggregate page).

Every control binds the SAME globalconfig key and callback as its original
page (display_text / display_ui); nothing here owns state. Advanced options
stay in their original pages behind the Advanced tabs.
"""

import functools

from qtsymbols import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QScrollArea,
    QFrame,
    QComboBox,
    QFontMetrics,
    QSizePolicy,
    Qt,
)

import gobject
from myutils.config import globalconfig, _TR
from myutils.textsource_selection import select_exclusive_text_source
from gui.setting.display_text import mayberealtimesetfont, createtextfontcom
from gui.usefulwidget import D_getsimpleswitch, D_getspinbox, D_getsimplecombobox
from gui.ltwidgets import LtPanelList, LtButton, lt_tokens


def _current_input_method():
    for key in ("texthook", "ocr", "copy"):
        if globalconfig["sourcestatus2"][key]["use"]:
            return key
    return "texthook"


def _set_input_method(key):
    # single active text source: the selected one on, the others off
    select_exclusive_text_source(globalconfig["sourcestatus2"], preferred=key)
    gobject.base.starttextsource(use=key, checked=True)


JAPANESE_TTS_VOICES = [
    ("Nanami　·　自然女声（默认）", "ja-JP-NanamiNeural"),
    ("Keita　·　自然男声", "ja-JP-KeitaNeural"),
]


def _set_japanese_tts_voice(voice):
    for reader_name in globalconfig["reader"]:
        globalconfig["reader"][reader_name]["use"] = reader_name == "edgetts"
    globalconfig["reader"]["edgetts"]["voice"] = voice
    gobject.base.startreader(use="edgetts", checked=True)


def _create_japanese_voice_combo():
    labels = [name for name, _ in JAPANESE_TTS_VOICES]
    combo = D_getsimplecombobox(
        labels,
        globalconfig["reader"]["edgetts"],
        "voice",
        internal=[voice for _, voice in JAPANESE_TTS_VOICES],
        callback=_set_japanese_tts_voice,
        default="ja-JP-NanamiNeural",
        sizeX=True,
    )()

    # The generic compact combo elides long labels. This selector needs to show
    # the complete voice name/type in both its closed state and popup list.
    text_width = max(QFontMetrics(combo.font()).horizontalAdvance(x) for x in labels)
    full_width = max(260, text_width + 56)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    combo.setMinimumWidth(full_width)
    combo.setSizePolicy(
        QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
    )
    combo.view().setMinimumWidth(full_width)
    combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
    return combo


def _section_card(title, subtitle, panel):
    """Give the aggregate page explicit hierarchy and breathing room."""
    tokens = lt_tokens()
    panel.setGraphicsEffect(None)
    for row in panel._rows:
        row.setMinimumHeight(58)
    section = QWidget()
    section_lay = QVBoxLayout(section)
    section_lay.setContentsMargins(0, 0, 0, 0)
    section_lay.setSpacing(9)
    heading = QLabel(_TR(title))
    heading.setStyleSheet(
        "QLabel { color: %s; font-size: %s; font-weight: 650; "
        "background: transparent; padding-left: 4px; }"
        % (tokens["text"], tokens["size_title"])
    )
    section_lay.addWidget(heading)
    if subtitle:
        description = QLabel(_TR(subtitle))
        description.setWordWrap(True)
        description.setStyleSheet(
            "QLabel { color: %s; font-size: %s; background: transparent; "
            "padding-left: 4px; }"
            % (tokens["text2"], tokens["size_secondary"])
        )
        section_lay.addWidget(description)
    section_lay.addWidget(panel)
    return section


def setTabQuick(self, basel):
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(24, 22, 24, 30)
    lay.setSpacing(22)

    tt = gobject.base.translation_ui.translate_text

    # ---- Text input method (dropdown) ---------------------------------
    _method_keys = ["texthook", "ocr", "copy"]
    _method_combo = QComboBox()
    _method_combo.addItems(["Hook", "OCR", "Clipboard"])
    _method_combo.setCurrentIndex(_method_keys.index(_current_input_method()))
    _method_combo.currentIndexChanged.connect(
        lambda i: _set_input_method(_method_keys[i])
    )
    rec = LtPanelList()
    rec.add_row(
        title=_TR("文本输入方式"),
        subtitle=_TR("默认使用 Hook，可随时切换"),
        control=_method_combo,
    )
    lay.addWidget(
        _section_card("文本输入", "选择当前获取游戏文字的方式", rec)
    )

    # ---- Typography ----------------------------------------------------
    typography = LtPanelList()
    typography.add_row(title=_TR("日文字体"), control=createtextfontcom("fonttype"))
    typography.add_row(
        title=_TR("字体大小"),
        control=D_getspinbox(
            5, 100, globalconfig, "fontsizeori", double=True,
            callback=mayberealtimesetfont, default=16,
        )(),
    )
    lay.addWidget(
        _section_card("文字显示", "调整日文原文的字体与阅读尺寸", typography)
    )

    # ---- Reading -------------------------------------------------------
    read = LtPanelList()
    read.add_row(
        title=_TR("日语朗读音色"),
        subtitle=_TR("默认音色：Nanami　 · 　在线自然发音（需要网络）"),
        control=_create_japanese_voice_combo(),
    )
    read.add_row(
        title=_TR("振假名（注音）"),
        control=D_getsimpleswitch(
            globalconfig, "isshowhira",
            callback=lambda x: tt.showhidert(x), default=True,
        )(),
    )
    read.add_row(
        title=_TR("分词高亮"),
        control=D_getsimpleswitch(
            globalconfig, "show_fenci",
            callback=lambda _: tt.setfontstyle(), default=True,
        )(),
    )
    read.add_row(
        title=_TR("点词查词"),
        control=D_getsimpleswitch(
            globalconfig, "usesearchword",
            callback=lambda _: tt.showhideclick(), default=True,
        )(),
    )
    read.add_row(
        title=_TR("悬浮单词提示"),
        control=D_getsimpleswitch(
            globalconfig, "word_hover_show_word_info",
            callback=lambda _: tt.showhideclick(), default=False,
        )(),
    )
    lay.addWidget(
        _section_card(
            "日语学习",
            "控制注音、结构提示、点词查词与日语朗读",
            read,
        )
    )

    # ---- Overlay -------------------------------------------------------
    ov = LtPanelList()
    ov.add_row(
        title=_TR("悬浮窗模式"),
        control=D_getsimplecombobox(
            [_TR("紧凑"), _TR("展开")],
            globalconfig, "overlay_mode",
            internal=["compact", "expanded"],
            callback=lambda _: tt.setoverlaymode(globalconfig.get("overlay_mode", "compact")),
            default="compact",
        )(),
    )
    ov.add_row(
        title=_TR("背景透明"),
        control=D_getsimpleswitch(
            globalconfig, "backtransparent",
            callback=lambda _: gobject.base.translation_ui.set_color_transparency(),
            default=False,
        )(),
    )
    lay.addWidget(
        _section_card("悬浮窗", "调整阅读窗口的布局与背景", ov)
    )

    # ---- Appearance ----------------------------------------------------
    app_ = LtPanelList()
    app_.add_row(
        title=_TR("明暗"),
        control=D_getsimplecombobox(
            [_TR("跟随系统"), _TR("亮色"), _TR("暗色")],
            globalconfig, "darklight2",
            internal=[0, 1, 2],
            default=0,
            callback=lambda _: gobject.base.setcommonstylesheet(),
        )(),
    )
    app_.add_row(
        title=_TR("主题"),
        control=D_getsimplecombobox(
            [_TR("学习（默认）"), "QTWin11", "PyQtDarkTheme"],
            globalconfig, "theme3",
            internal=["", "QTWin11", "PyQtDarkTheme"],
            default="",
            callback=lambda _: gobject.base.setcommonstylesheet(),
        )(),
    )
    lay.addWidget(
        _section_card("外观", "选择明暗模式与整体主题", app_)
    )

    # ---- Shortcuts -----------------------------------------------------
    misc = LtPanelList()
    misc.add_row(
        title=_TR("快捷键"),
        subtitle=_TR("在快捷键页面中管理所有快捷键"),
        control=LtButton(
            _TR("快捷键…"),
            variant="secondary",
            clicked=lambda: self.tab_widget.setCurrentIndex(7),
        ),
    )
    lay.addWidget(_section_card("快捷操作", "", misc))
    lay.addStretch(1)
    # wrap in a scroll area so the page never clips when the window is short
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    basel.addWidget(scroll)
