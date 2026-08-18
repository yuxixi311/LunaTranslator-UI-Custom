"""
LunaTranslator Learning UI - reusable primitives built on designtokens.

Each primitive carries an `ltClass` dynamic property; the generated QSS
(myutils.designtokens.qss) styles it. Until the QSS is wired globally
(steps 9/10), primitives apply the token stylesheet to themselves so they
render correctly standalone.

Conventions:
  - one accent, hairline dividers, token radii/heights only
  - translucency only where surfaces overlap content (see DESIGNS_SYSTEM)
  - animations animate opacity/geometry only, 120-220 ms, reduced-motion aware
"""

from qtsymbols import (
    QWidget,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    QSize,
    Qt,
    QColor,
    pyqtSignal,
)

from myutils.designtokens import qss, resolve_theme, EASE


def lt_isdark():
    """Current dark/light state using the app's existing resolution."""
    from myutils.utils import nowisdark

    return bool(nowisdark())


def lt_tokens():
    return resolve_theme(lt_isdark())


def _apply_qss(widget):
    """Apply the token QSS to a widget tree (temporary until global wiring)."""
    widget.setStyleSheet(qss(lt_tokens()))


def _ltclass(widget, cls):
    widget.setProperty("ltClass", cls)
    return widget


def _shadow(widget, tier, dy=None, blur=None, alpha=None):
    blur_, dy_, alpha_ = lt_tokens()["sh_" + tier]
    if blur is not None:
        blur_ = blur
    if dy is not None:
        dy_ = dy
    if alpha is not None:
        alpha_ = alpha
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur_)
    eff.setOffset(0, dy_)
    eff.setColor(QColor(0, 0, 0, int(alpha_ * 255)))
    widget.setGraphicsEffect(eff)
    return eff


def lt_reduced_motion():
    """Windows 'Show animations in windows' setting (SPI_GETCLIENTAREAANIMATION)."""
    try:
        import windows

        return not bool(windows.SystemParametersInfo(0x1042, 0, None, 0))  # SPI_GETCLIENTAREAANIMATION
    except Exception:
        return False


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------


class LtButton(QPushButton):
    """variant: primary | secondary | quiet | danger"""

    def __init__(self, text="", variant="secondary", parent=None, clicked=None):
        super().__init__(text, parent)
        _ltclass(self, variant)
        _apply_qss(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if clicked is not None:
            self.clicked.connect(clicked)


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------


class LtPanel(QFrame):
    """Unified surface panel: hairline border, token radius, optional shadow."""

    def __init__(self, parent=None, shadow_tier=None, radius=None):
        super().__init__(parent)
        _ltclass(self, "surface")
        _apply_qss(self)
        if radius is not None:
            self.setStyleSheet(
                self.styleSheet()
                + f"\nQFrame {{ border-radius: {radius}px; }}"
            )
        if shadow_tier:
            _shadow(self, shadow_tier)


class LtHairline(QFrame):
    """1px hairline divider."""

    def __init__(self, parent=None):
        super().__init__(parent)
        t = lt_tokens()
        self.setFixedHeight(1)
        self.setStyleSheet(f"QFrame {{ border: none; background: {t['hairline']}; }}")


# --------------------------------------------------------------------------
# Unified panel list (the anti-fragmentation pattern)
# --------------------------------------------------------------------------


class LtListRow(QWidget):
    """One row: optional title+subtitle left, control right, hairline between rows."""

    def __init__(self, title=None, subtitle=None, control=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)
        if title is not None or subtitle is not None:
            txt = QVBoxLayout()
            txt.setSpacing(2)
            if title is not None:
                lbl = QLabel(title)
                t = lt_tokens()
                lbl.setStyleSheet(
                    f"QLabel {{ color: {t['text']}; font-size: {t['size_body']}; font-weight: 600; background: transparent; }}"
                )
                txt.addWidget(lbl)
            if subtitle is not None:
                sub = QLabel(subtitle)
                t = lt_tokens()
                sub.setWordWrap(True)
                sub.setStyleSheet(
                    f"QLabel {{ color: {t['text2']}; font-size: {t['size_secondary']}; background: transparent; }}"
                )
                txt.addWidget(sub)
            lay.addLayout(txt, 1)
        if control is not None:
            lay.addWidget(control, 0)
        # hairline below every row by default; LtPanelList re-marks the last row
        t = lt_tokens()
        self.setStyleSheet(
            f"QWidget {{ background: {t['surface']}; border-bottom: 1px solid {t['hairline']}; }}"
        )


class LtPanelList(QWidget):
    """Unified panel of hairline-separated rows."""

    def __init__(self, rows=None, parent=None):
        super().__init__(parent)
        _ltclass(self, "surface")
        _apply_qss(self)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._rows = []
        if rows:
            for r in rows:
                self.add_row(**r)

    def add_row(self, **kw):
        kw.pop("last", None)
        row = LtListRow(**kw)
        self._rows.append(row)
        # rows are re-marked so only the last one lacks the hairline
        for i, _r in enumerate(self._rows):
            t = lt_tokens()
            if i == len(self._rows) - 1:
                _r.setStyleSheet(f"QWidget {{ background: {t['surface']}; }}")
            else:
                _r.setStyleSheet(
                    f"QWidget {{ background: {t['surface']}; border-bottom: 1px solid {t['hairline']}; }}"
                )
        self._lay.addWidget(row)
        return row


# --------------------------------------------------------------------------
# Inputs (thin wrappers; QSS does the styling once wired globally)
# --------------------------------------------------------------------------


class LtLineEdit(QLineEdit):
    def __init__(self, text="", placeholder="", parent=None):
        super().__init__(text, parent)
        _apply_qss(self)
        if placeholder:
            self.setPlaceholderText(placeholder)


class LtComboBox(QComboBox):
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        _apply_qss(self)
        if items:
            self.addItems(items)


# --------------------------------------------------------------------------
# Segmented control (pill)
# --------------------------------------------------------------------------


class LtSegmented(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, options, current=None, parent=None):
        """options: list of (key, label)"""
        super().__init__(parent)
        t = lt_tokens()
        self._keys = [k for k, _ in options]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.setStyleSheet(
            f"LtSegmented {{ background: {t['track']}; border-radius: {t['r_pill']}px; }}"
        )
        self._buttons = {}
        for key, label in options:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self._select(k, emit=True))
            self._buttons[key] = b
            lay.addWidget(b)
        self._restyle()
        if current in self._keys:
            self._select(current, emit=False)

    def _restyle(self):
        t = lt_tokens()
        dark = lt_isdark()
        active_bg = "#FFFFFF" if not dark else t["text"]
        active_fg = t["text"] if not dark else "#000000"
        for key, b in self._buttons.items():
            active = b.isChecked()
            b.setStyleSheet(
                f"QPushButton {{ border: none; padding: 5px 14px; border-radius: {t['r_pill']}px; "
                f"background: {'transparent' if not active else active_bg}; "
                f"color: {t['text2'] if not active else active_fg}; "
                f"font-size: {t['size_secondary']}; "
                f"{'font-weight: 600;' if active else ''} }}"
            )

    def _select(self, key, emit=False):
        for k, b in self._buttons.items():
            b.setChecked(k == key)
        self._restyle()
        if emit:
            self.changed.emit(key)

    def current(self):
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return None


# --------------------------------------------------------------------------
# Status dot (recognition live indicator; pulse is disable-able)
# --------------------------------------------------------------------------


class LtStatusDot(QWidget):
    def __init__(self, parent=None, pulsing=True):
        super().__init__(parent)
        t = lt_tokens()
        self.setFixedSize(7, 7)
        self._color = t["live"]
        self._anim = None
        self.set_pulsing(pulsing)

    def set_pulsing(self, on):
        if on and self._anim is None and not lt_reduced_motion():
            eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(eff)
            self._anim = QPropertyAnimation(eff, b"opacity", self)
            self._anim.setDuration(1100)
            self._anim.setStartValue(1.0)
            self._anim.setKeyValueAt(0.5, 0.35)
            self._anim.setEndValue(1.0)
            self._anim.setLoopCount(-1)
            self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            self._anim.start()
        elif not on and self._anim is not None:
            self._anim.stop()
            self._anim = None
            self.setGraphicsEffect(None)

    def set_live(self, live):
        t = lt_tokens()
        self._color = t["live"] if live else t["text4"]
        self.update()

    def paintEvent(self, _):
        from qtsymbols import QPainter, QBrush

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(self._color)))
        p.drawEllipse(0, 0, 7, 7)
        p.end()
