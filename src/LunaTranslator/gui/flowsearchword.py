from qtsymbols import *
import functools
import gobject, NativeUtils, windows
from myutils.config import globalconfig, _TR
from gui.usefulwidget import (
    ColorButton,
    getspinbox,
    getsimpleswitch,
    getsmalllabel,
    getIconButton,
    resizableframeless,
    SplitLine,
    getsimplecombobox,
    getboxlayout,
    limitpos,
)
from gui.showword import WordViewer
from gui.dynalang import LDialog, LFormLayout


class DraggableQWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.setMouseTracking(True)
        self.mouse_press_pos = None
        self.window_pos_at_press = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = event.globalPos()
            self.window_pos_at_press = self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.mouse_press_pos:
            move_pos = event.globalPos() - self.mouse_press_pos
            new_window_pos = self.window_pos_at_press + move_pos
            self.move(new_window_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_press_pos = None
        super().mouseReleaseEvent(event)


def createsomecontrols(
    callbackR, callbackDWM, kR, kRsys, kRsysDf, kDWM, kshadow, needcheck=True
):
    def ___(callbackX, _):
        callbackX()

    spin1 = getspinbox(
        0, 50, globalconfig, kR, callback=functools.partial(___, callbackR)
    )
    sw = None
    effectlayout = None
    if needcheck:

        def __vRsys(kRsys, kRsysDf):
            return gobject.sys_ge_win_11 and globalconfig.get(kRsys, kRsysDf)

        vRsys = functools.partial(__vRsys, kRsys, kRsysDf)

        def __vR(kDWM, vRsys):
            return globalconfig.get(kDWM, 0) == 0 and not vRsys()

        def __yinyinguse(kDWM, vRsys):
            return globalconfig.get(kDWM, 0) != 0 and not vRsys()

        vR = functools.partial(__vR, kDWM, vRsys)
        if not vR():
            spin1.hide()
        yinyinguse = functools.partial(__yinyinguse, kDWM, vRsys)
        __shadowxx = getsmalllabel("阴影")()
        __shadowxx2 = getsimpleswitch(
            globalconfig,
            kshadow,
            callback=functools.partial(___, callbackDWM),
            default=True,
        )

        def __cb2(
            spin1: QSpinBox,
            vR,
            __shadowxx: QLabel,
            yinyinguse,
            __shadowxx2: QLabel,
            callbackR,
            _,
        ):
            spin1.setVisible(vR()),
            __shadowxx.setVisible(yinyinguse()),
            __shadowxx2.setVisible(yinyinguse()),
            callbackR()

        if gobject.sys_ge_win_11:
            sw = getsimpleswitch(
                globalconfig,
                kRsys,
                default=kRsysDf,
                callback=functools.partial(
                    __cb2, spin1, vR, __shadowxx, yinyinguse, __shadowxx2, callbackR
                ),
            )

        if not yinyinguse():
            __shadowxx.hide()
            __shadowxx2.hide()
        __shadowxx = __shadowxx
        __shadowxx2 = __shadowxx2

        def __cb(
            yinyinguse,
            __shadowxx: QLabel,
            __shadowxx2: QLabel,
            spin1: QSpinBox,
            callbackR,
            callbackDWM,
            _,
        ):
            __shadowxx.setVisible(yinyinguse())
            __shadowxx2.setVisible(yinyinguse())
            spin1.setVisible(vR())
            callbackR()
            callbackDWM()

        effectlayout = getboxlayout(
            [
                getsimplecombobox(
                    ["Disable", "Acrylic", "Aero"],
                    globalconfig,
                    kDWM,
                    callback=functools.partial(
                        __cb,
                        yinyinguse,
                        __shadowxx,
                        __shadowxx2,
                        spin1,
                        callbackR,
                        callbackDWM,
                    ),
                    default=0,
                ),
                __shadowxx,
                __shadowxx2,
            ],
        )
    return getboxlayout([spin1, "", "使用系统圆角", sw]) if sw else spin1, effectlayout


class dialog_syssetting(LDialog):
    def __init__(self, parent: "WordViewTooltip") -> None:
        super().__init__(parent, Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("其他设置")
        formLayout = LFormLayout(self)

        formLayout.addRow(
            "自动朗读",
            getsimpleswitch(globalconfig, "is_search_word_auto_tts_2", default=False),
        )
        focus = getsimpleswitch(
            globalconfig,
            "WordViewTooltipHideFocus",
            callback=lambda x: parent.closebutton.setVisible(
                not (
                    globalconfig["WordViewTooltipHideFocus"]
                    or globalconfig["WordViewTooltipHideLeave"]
                )
            ),
        )
        focus.setEnabled(not globalconfig["WordViewTooltipHideLeave"])
        formLayout.addRow(
            "鼠标离开时关闭",
            getsimpleswitch(
                globalconfig,
                "WordViewTooltipHideLeave",
                callback=lambda x: (
                    focus.setEnabled(not x),
                    parent.closebutton.setVisible(
                        not (
                            globalconfig["WordViewTooltipHideFocus"]
                            or globalconfig["WordViewTooltipHideLeave"]
                        )
                    ),
                ),
            ),
        )
        formLayout.addRow("失去焦点时关闭", focus)
        formLayout.addRow(SplitLine())
        spin = getspinbox(
            0,
            50,
            globalconfig,
            "WordViewTooltipBorder",
            callback=lambda _: parent.doResize(),
        )
        formLayout.addRow("边距", spin)

        spin1, lay = createsomecontrols(
            lambda: parent.setbgcolor(),
            lambda: parent.seteffect(),
            "WordViewTooltipRadius",
            "WordViewTooltipRadiusSys",
            gobject.sys_ge_win_11,
            "WordViewTooltipDWM",
            "WordViewTooltipDWM_1",
        )
        formLayout.addRow("圆角", spin1)

        formLayout.addRow("窗口特效", lay)
        color11 = ColorButton(
            self,
            globalconfig,
            "WordViewTooltipColor",
            callback=lambda _: parent.setbgcolor(),
            alpha=True,
            tips="背景颜色",
            cantzeroalpha=True,
        )
        formLayout.addRow("背景颜色", color11)
        color1 = ColorButton(
            self,
            globalconfig,
            "WordViewTooltipContentColor",
            callback=lambda _: parent.setbgcolor(),
            alpha=True,
            tips="内容背景颜色",
        )
        formLayout.addRow("内容背景颜色", color1)

        self.exec()


class WordViewTooltip(resizableframeless, DraggableQWidget):

    def close(self):
        self._dismiss_lookup()
        self.hide()

    def _dismiss_lookup(self):
        # Dictionary workers may finish after the popup has been dismissed.
        # Keep readyData for the full-window/Anki buttons, but reject callbacks.
        self._dismissed_hover_key = self._lookup_key
        self._lookup_key = None
        self._focus_dismissed_key = None
        self._focus_dismissed_token = None
        self._awaiting_source_press = False
        self.__f.stop()
        self.__savestatus = None
        if self.__state == 2:
            self.view.cancel_search()
        self.lastword = None

    @property
    def gripSize(self):
        return globalconfig["WordViewTooltipBorder"]

    def leaveEvent(self, a0: QEvent):
        if globalconfig["WordViewTooltipHideLeave"]:
            if not self.geometry().contains(QCursor.pos()):
                self.close()
        return super().leaveEvent(a0)

    def focusOutEvent(self, a0):
        if globalconfig["WordViewTooltipHideFocus"]:
            focused_widget = QApplication.focusWidget()
            if (
                focused_widget
                and (focused_widget is self or self.isAncestorOf(focused_widget))
            ):
                pass
            else:
                # Focus can leave on mouse press, while the renderer dispatches
                # the lookup on release. Remember only this source interaction;
                # leaving/changing the hovered word clears the one-use marker.
                source = gobject.base.translation_ui.translate_text
                same_source_press = (
                    self._lookup_key is not None
                    and source.rect().contains(source.mapFromGlobal(QCursor.pos()))
                    and (
                        windows.GetAsyncKeyState(windows.VK_LBUTTON) < 0
                        or windows.GetAsyncKeyState(windows.VK_RBUTTON) < 0
                    )
                )
                key = self._lookup_key if same_source_press else None
                self.close()
                self._focus_dismissed_key = key
                if key is not None:
                    self._focus_dismissed_token = self._source_pressed_token
                    self._awaiting_source_press = self._source_pressed_token is None
        return super().focusOutEvent(a0)

    def doResize(self):
        self.wbutton.setGeometry(
            self.gripSize,
            self.gripSize,
            self.width() - 2 * self.gripSize,
            self.wbutton.height(),
        )
        self.view.setGeometry(
            self.gripSize,
            self.gripSize + self.wbutton.height(),
            self.width() - 2 * self.gripSize,
            self.height() - 2 * self.gripSize - self.wbutton.height(),
        )

    def resizeEvent(self, a0: QResizeEvent):
        if self.__state == 2:
            # Qt模式下，谜之resize
            self.doResize()
            globalconfig["WordViewTooltip2"] = a0.size().width(), a0.size().height()
        return super().resizeEvent(a0)

    def setbgcolor(self):

        NativeUtils.SetCornerNotRound(
            int(self.winId()),
            False,
            globalconfig.get("WordViewTooltipRadiusSys", gobject.sys_ge_win_11),
        )
        radiu_valid = globalconfig.get("WordViewTooltipDWM", 0) == 0 and not (
            gobject.sys_ge_win_11
            and globalconfig.get("WordViewTooltipRadiusSys", gobject.sys_ge_win_11)
        )
        color = globalconfig["WordViewTooltipColor"]
        r = globalconfig["WordViewTooltipRadius"]
        self.w.setStyleSheet(r""" 
        QLabel{background: %s; 
        border-radius: %spx}
 """ % (color, r * radiu_valid))
        self.w2.setStyleSheet(r""" 
        QLabel{background: %s;border-radius: 0px; }
 """ % (globalconfig["WordViewTooltipContentColor"]))

    def seteffect(self):
        if globalconfig.get("WordViewTooltipDWM", 0) == 0:
            NativeUtils.clearEffect(int(self.winId()))
        elif globalconfig.get("WordViewTooltipDWM", 0) == 1:
            NativeUtils.setAcrylicEffect(
                int(self.winId()),
                globalconfig.get("WordViewTooltipDWM_1", True),
                0x00FFFFFF,
            )
        elif globalconfig.get("WordViewTooltipDWM", 0) == 2:
            NativeUtils.setAeroEffect(
                int(self.winId()), globalconfig.get("WordViewTooltipDWM_1", True)
            )

    def __load(self):
        if self.__state != 0:
            return
        self.__state = 1
        self.setupUi()
        self.__state = 2

    def __init__(self, parent):
        DraggableQWidget.__init__(self)
        resizableframeless.__init__(
            self,
            parent,
            flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.__state = 0
        gobject.base.hover_search_word.connect(self.searchword)
        gobject.base.click_search_word.connect(self._click_searchword)
        gobject.base.lookup_source_pressed.connect(self.source_press)
        gobject.base.lookup_source_released.connect(self.source_release)
        self.__f = QTimer(self)
        self.__f.setInterval(50)
        self.__f.timeout.connect(self.__detectkey)
        self.__savestatus = None
        self._lookup_key = None
        self._dismissed_hover_key = None
        self._source_hover_key = None
        self._focus_dismissed_key = None
        self._focus_dismissed_token = None
        self._awaiting_source_press = False
        self._source_pressed_token = None
        self._source_latest_token = None
        self._source_consumed_token = None

    def source_press(self, token):
        if token == self._source_latest_token:
            return  # The same Qt event can propagate through child/parent.
        self._source_latest_token = token
        self._source_pressed_token = token
        if self._awaiting_source_press:
            self._focus_dismissed_token = token
            self._awaiting_source_press = False
        else:
            self._focus_dismissed_key = None
            self._focus_dismissed_token = None

    def source_release(self, token):
        if token == self._source_pressed_token:
            self._source_pressed_token = None

    def _click_searchword(self, word, sentence, append, token):
        self.searchword(word, sentence, append, click_token=token)

    def observe_source_word(self, word, sentence):
        key = (word.strip(), sentence)
        if key != self._source_hover_key:
            self._focus_dismissed_key = None
            self._focus_dismissed_token = None
            self._awaiting_source_press = False
        self._source_hover_key = key

    def Leave(self, source_left=True):
        self.__f.stop()
        self.__savestatus = None
        self.lastword = None
        self._dismissed_hover_key = None
        if source_left:
            self._source_hover_key = None
            self._source_pressed_token = None
            self._focus_dismissed_key = None
            self._focus_dismissed_token = None
            self._awaiting_source_press = False

    def setupUi(self):
        self.lastword = None
        self.setMouseTracking(True)

        self.setMinimumHeight(300)
        self.setMinimumWidth(300)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        w = QLabel(self)
        w.setMouseTracking(True)
        self.w = w
        w2 = QLabel(self)
        self.w2 = w2
        self.setbgcolor()
        self.seteffect()
        self.wbutton = QWidget(self)
        self.wbutton.setMouseTracking(True)
        self.wbutton.setObjectName("fuck")
        self.wbutton.setStyleSheet("QWidget#fuck{background:transparent}")
        buttons = QHBoxLayout(self.wbutton)
        buttons.setContentsMargins(0, 0, 0, 0)
        self.closebutton = getIconButton(
            icon="fa.times", callback=self.close, tips="关闭"
        )
        if (
            globalconfig["WordViewTooltipHideFocus"]
            or globalconfig["WordViewTooltipHideLeave"]
        ):
            self.closebutton.hide()
        buttons.addWidget(self.closebutton)
        buttons.addWidget(
            getIconButton(
                icon="fa.music",
                callback=lambda: gobject.base.read_text(self.view.currWord),
                tips="语音合成",
            )
        )
        self.wordlabel = QLabel()
        self.wordlabel.setTextFormat(Qt.TextFormat.PlainText)
        self.wordlabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons.addWidget(self.wordlabel)
        searchword = lambda anki: (
            self.close(),
            gobject.base.searchwordW.move(self.pos()),
            gobject.base.searchwordW._click_word_search_function(
                self.view.currWord, self.view.save_sentence, False, self.view.readyData
            ),
            (
                gobject.base.searchwordW.ankiconnect.click()
                if ((anki ^ gobject.base.searchwordW.ankiconnect.isChecked()))
                else ""
            ),
        )
        buttons.addWidget(
            getIconButton(
                icon="fa.search",
                callback=lambda: (searchword(False)),
                tips="查词",
            )
        )
        buttons.addWidget(
            getIconButton(
                icon="fa.adn",
                callback=lambda: (searchword(True)),
                tips="Anki",
            )
        )
        buttons.addWidget(
            getIconButton(
                callback=functools.partial(dialog_syssetting, self), tips="设置"
            )
        )
        self.view = WordViewer(self, tabonehide=True, transp=True)
        self.view.use_bg_color_parser = True
        self.setCentralWidget(w)
        self.view.first_result_shown.connect(self.showresult)
        self.view.from_webview_search_word.connect(
            self._search_from_popup
        )
        self.view.from_webview_search_word_in_new_window.connect(
            lambda w: gobject.base.searchwordW.searchwinnewwindow(w)
        )
        self.view.tab.setStyleSheet("background:transparent")
        self.view.internalsizechanged.connect(self.w2.resize)
        self.view.internalmoved.connect(
            lambda pos: self.w2.move(self.view.mapToParent(pos))
        )

    def __detectkey(self):
        if not self.__savestatus or not globalconfig.get("usesearchword_S_hover", False):
            self.__f.stop()
            return
        result = gobject.base.checkkeypresssatisfy("searchword_S_hover", False)
        result = result == -1 or result == True
        if result:
            self.__f.stop()
            self.searchword(*self.__savestatus)

    def closeEvent(self, event):
        self._dismiss_lookup()
        return super().closeEvent(event)

    def _set_word_status(self, word, completed=False):
        self.wordlabel.setText(
            "{} · {}".format(word, _TR("已查词" if completed else "查询中"))
        )

    def _search_from_popup(self, word):
        # Dictionary links/selection menus remain explicit searches, not toggles.
        # Moving to another entry also ends the previous source-word identity.
        if self._lookup_key is None:
            return
        word = word.strip()
        if not word:
            return
        self.__f.stop()
        self.__savestatus = None
        self._lookup_key = (word, None)
        self._dismissed_hover_key = None
        self._focus_dismissed_key = None
        self._focus_dismissed_token = None
        self._awaiting_source_press = False
        self._set_word_status(word)
        self.view.searchword(word)

    def searchword(
        self,
        word: str,
        sentence=None,
        append=False,
        fromhover=False,
        show=False,
        force=False,
        click_token="",
    ):
        self.__load()
        if self.__state != 2:
            return
        word = word.strip()
        if not word:
            return
        key = (word, sentence)
        if not fromhover and click_token:
            # Renderer events precede the threaded click callback. Reject an
            # older/duplicate release after a newer navigation or gesture.
            if (
                click_token != self._source_latest_token
                or click_token == self._source_consumed_token
            ):
                return
            self._source_consumed_token = click_token
        if (
            not fromhover
            and key == self._focus_dismissed_key
            and click_token == self._focus_dismissed_token
        ):
            self._focus_dismissed_key = None
            self._focus_dismissed_token = None
            return
        if not fromhover and key == self._lookup_key:
            # Right click normally appends. Toggle before append and auto-TTS,
            # including while the first dictionary response is still pending.
            self.close()
            return
        if fromhover and key == self._dismissed_hover_key:
            return
        if fromhover and not force:
            if key == self.lastword:
                return self.moveresult_1()
            self.lastword = key
            if not show:
                self.__savestatus = word, sentence, append, fromhover, True, True
                self.__f.start()
                return
        self.__f.stop()
        self.__savestatus = None
        self._dismissed_hover_key = None
        self._focus_dismissed_key = None
        self._focus_dismissed_token = None
        self._awaiting_source_press = False
        self._lookup_key = key
        if not fromhover:
            self._source_hover_key = key
        self.savepos = QCursor.pos()
        if globalconfig.get("is_search_word_auto_tts_2", False):
            gobject.base.read_text(word)
        if append:
            word = self.view.currWord + word
        unuse = globalconfig[("ignoredict_S_click", "ignoredict_S_hover")[fromhover]]
        self._set_word_status(word)
        self.view.searchword(word, sentence, unuse=unuse)

    def showresult(self):
        if self._lookup_key is None:
            return
        self._set_word_status(self.view.currWord, completed=True)
        size = globalconfig.get("WordViewTooltip2")
        if size:
            self.resize(size[0], size[1])
        # 1 系统圆角时会谜之遮挡鼠标
        self.move(limitpos(self.savepos, self, QPoint(1, 10)))
        self.show()
        self.setFocus()
        from gui.rendertext.tooltipswidget import tooltipswidget

        tooltipswidget.hidetooltipwindow(source_left=False)

    def moveresult_1(self):
        if not self.isVisible():
            return
        result = gobject.base.checkkeypresssatisfy("searchword_S_hover", False)
        # 仅按着键盘时，才追踪，否则不要动。
        if result == True:
            self.move(limitpos(QCursor.pos(), self, QPoint(1, 10)))
