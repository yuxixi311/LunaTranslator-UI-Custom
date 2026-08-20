"""
LunaTranslator Learning UI - 常用设置 (frequently used settings aggregate page).

Every control binds the SAME globalconfig key and callback as its original
page (display_text / display_ui); nothing here owns state. Advanced options
stay in their original pages behind the Advanced tabs.
"""

import functools

from qtsymbols import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame

import gobject
from myutils.config import globalconfig, _TR
from gui.setting.display_text import mayberealtimesetfont, createtextfontcom
from gui.usefulwidget import D_getsimpleswitch, D_getspinbox, D_getsimplecombobox
from gui.ltwidgets import LtPanelList, LtButton, LtSegmented


def _active_ocr_name():
    use = globalconfig["ocr"].get("use")
    if use and use in globalconfig["ocr"]:
        return globalconfig["ocr"][use].get("name", use)
    return _TR("未选择")


def setTabQuick(self, basel):
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(16)

    tt = gobject.base.translation_ui.translate_text

    # ---- Recognition ---------------------------------------------------
    rec = LtPanelList()
    rec.add_row(
        title=_TR("OCR 引擎"),
        subtitle=_active_ocr_name(),
        control=LtButton(
            _TR("更改…"),
            variant="secondary",
            clicked=lambda: self.tab_widget.setCurrentIndex(1),
        ),
    )
    lay.addWidget(rec)

    # ---- Reading -------------------------------------------------------
    read = LtPanelList()
    read.add_row(title=_TR("日文字体"), control=createtextfontcom("fonttype"))
    read.add_row(
        title=_TR("字体大小"),
        control=D_getspinbox(
            5, 100, globalconfig, "fontsizeori", double=True,
            callback=mayberealtimesetfont, default=16,
        )(),
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
    lay.addWidget(read)

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
    lay.addWidget(ov)

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
    lay.addWidget(app_)

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
    lay.addWidget(misc)
    lay.addStretch(1)
    # wrap in a scroll area so the page never clips when the window is short
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    basel.addWidget(scroll)
