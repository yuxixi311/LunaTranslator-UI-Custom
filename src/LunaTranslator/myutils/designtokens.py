"""
LunaTranslator Learning UI - centralized design tokens.

Single source of truth for every visual value (PROJECT_CHARTER.md 17,
docs/DESIGN_SYSTEM.md). One token set generates:
  - qss(): QSS for Qt surfaces (settings window, dialogs, lists)
  - css(): CSS custom properties + base styles for the WebView2 reading overlay

Rules:
  - call sites reference tokens, never raw values
  - no imports from the rest of the application (standalone + testable)
  - light/dark share the exact same key set
"""

import re

# --------------------------------------------------------------------------
# Token definitions
# --------------------------------------------------------------------------

LIGHT = {
    # colors
    "bg": "#F5F5F7",
    "surface": "#FFFFFF",
    "hover": "#FBFBFD",
    "text": "#1D1D1F",
    "text2": "#6E6E73",
    "text3": "#86868B",
    "text4": "#AEAEB2",
    "hairline": "rgba(0, 0, 0, 0.08)",
    "accent": "#0071E3",
    "accent_pressed": "#0066CC",
    "accent_tint": "rgba(0, 113, 227, 0.08)",
    "focus_ring": "rgba(0, 113, 227, 0.35)",
    "selection": "rgba(0, 113, 227, 0.15)",
    "track": "#E8E8ED",
    "danger": "#FF3B30",
    "warning": "#FF9F0A",
    "success": "#30D158",
    "live": "#30D158",
    "scrim": "rgba(0, 0, 0, 0.28)",
    # surface alphas (translucent solid - the sanctioned glass substitute)
    "overlay_glass": "rgba(255, 255, 255, 0.86)",
    "glass_surface": "rgba(255, 255, 255, 0.72)",
    # typography (CJK-first so Latin and CJK render from one coherent family)
    "font_ui": '"Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif',
    "font_jp": '"Yu Gothic UI", "Meiryo UI", "Microsoft YaHei UI", sans-serif',
    "font_mono": '"Cascadia Mono", "Consolas", monospace',
    "size_display": "22px",
    "size_title": "17px",
    "size_body": "14px",
    "size_secondary": "13px",
    "size_caption": "12px",
    "size_small": "11px",
    # spacing scale (px)
    "s0": "2",
    "s1": "4",
    "s2": "8",
    "s3": "12",
    "s4": "16",
    "s5": "20",
    "s6": "24",
    "s8": "32",
    # radii (px)
    "r_control": "8",
    "r_panel": "12",
    "r_overlay": "18",
    "r_pill": "999",
    # control heights (px)
    "ctl_sm": "26",
    "ctl_md": "32",
    "ctl_lg": "40",
    # icons
    "icon_sm": "16",
    "icon_md": "20",
    "icon_lg": "22",
    "icon_stroke": "1.75",
    # motion (ms)
    "m_fast": "120",
    "m_default": "160",
    "m_slow": "220",
    # shadows: (blur, offset_y, alpha) - applied via QGraphicsDropShadowEffect in Qt
    "sh_window": (40, 8, 0.20),
    "sh_popup": (24, 4, 0.14),
    "sh_card": (16, 2, 0.08),
}

DARK = {
    "bg": "#161617",
    "surface": "#1C1C1E",
    "hover": "#232326",
    "text": "#F5F5F7",
    "text2": "#98989D",
    "text3": "#7C7C82",
    "text4": "#5A5A5E",
    "hairline": "rgba(255, 255, 255, 0.10)",
    "accent": "#2997FF",
    "accent_pressed": "#4DA9FF",
    "accent_tint": "rgba(41, 151, 255, 0.12)",
    "focus_ring": "rgba(41, 151, 255, 0.40)",
    "selection": "rgba(41, 151, 255, 0.20)",
    "track": "#2C2C2E",
    "danger": "#FF453A",
    "warning": "#FFD60A",
    "success": "#32D74B",
    "live": "#32D74B",
    "scrim": "rgba(0, 0, 0, 0.45)",
    "overlay_glass": "rgba(20, 20, 22, 0.88)",
    "glass_surface": "rgba(44, 44, 46, 0.72)",
    "font_ui": '"Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Segoe UI", sans-serif',
    "font_jp": '"Yu Gothic UI", "Meiryo UI", "Microsoft YaHei UI", sans-serif',
    "font_mono": '"Cascadia Mono", "Consolas", monospace',
    "size_display": "22px",
    "size_title": "17px",
    "size_body": "14px",
    "size_secondary": "13px",
    "size_caption": "12px",
    "size_small": "11px",
    "s0": "2",
    "s1": "4",
    "s2": "8",
    "s3": "12",
    "s4": "16",
    "s5": "20",
    "s6": "24",
    "s8": "32",
    "r_control": "8",
    "r_panel": "12",
    "r_overlay": "18",
    "r_pill": "999",
    "ctl_sm": "26",
    "ctl_md": "32",
    "ctl_lg": "40",
    "icon_sm": "16",
    "icon_md": "20",
    "icon_lg": "22",
    "icon_stroke": "1.75",
    "m_fast": "120",
    "m_default": "160",
    "m_slow": "220",
    "sh_window": (40, 8, 0.24),
    "sh_popup": (24, 4, 0.20),
    "sh_card": (16, 2, 0.14),
}

assert set(LIGHT) == set(DARK), "light/dark token keys must match"

# easing (Qt: QEasingCurve.OutCubic; CSS: the curve below)
EASE = "cubic-bezier(0.25, 1, 0.5, 1)"


def resolve_theme(is_dark):
    """Return the token dict for a dark/light flag."""
    return DARK if is_dark else LIGHT


def _v(t, key):
    return t[key]


# --------------------------------------------------------------------------
# QSS generation (Qt surfaces)
# --------------------------------------------------------------------------


def qss(theme):
    """Generate the application QSS from a token dict.

    Restrained by design: hairline borders, token radii, one accent.
    Widgets get their variant styles via dynamic properties set by the
    primitive layer (e.g. w.setProperty("ltClass", "primary")).
    """
    t = theme
    return f"""
/* LunaTranslator Learning UI - generated from designtokens (do not edit by hand) */

* {{
    font-family: {t["font_ui"]};
}}

QWidget {{
    background: {t["bg"]};
    color: {t["text"]};
    font-size: {t["size_body"]};
}}

QFrame[ltClass="surface"], QWidget[ltClass="surface"] {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_panel"]}px;
}}

QFrame[ltClass="glass"], QWidget[ltClass="glass"] {{
    background: {t["glass_surface"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_panel"]}px;
}}

QFrame[ltClass="hairline-bottom"] {{
    border: none;
    border-bottom: 1px solid {t["hairline"]};
}}

/* ---- buttons ---- */
QPushButton {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_control"]}px;
    padding: 4px {t["s3"]}px;
    min-height: {t["ctl_md"]}px;
}}
QPushButton:hover {{
    background: {t["hover"]};
}}
QPushButton:pressed {{
    background: {t["track"]};
}}
QPushButton:disabled {{
    color: {t["text4"]};
}}

QPushButton[ltClass="primary"] {{
    background: {t["accent"]};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton[ltClass="primary"]:hover {{
    background: {t["accent_pressed"]};
}}
QPushButton[ltClass="primary"]:pressed {{
    background: {t["accent_pressed"]};
}}

QPushButton[ltClass="quiet"] {{
    background: transparent;
    border: none;
    color: {t["text2"]};
}}
QPushButton[ltClass="quiet"]:hover {{
    background: {t["hover"]};
    color: {t["text"]};
}}

QPushButton[ltClass="danger"] {{
    background: transparent;
    border: 1px solid {t["hairline"]};
    color: {t["danger"]};
}}
QPushButton[ltClass="danger"]:hover {{
    background: {t["hover"]};
}}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_control"]}px;
    padding: 3px {t["s2"]}px;
    min-height: {t["ctl_md"]}px;
    selection-background-color: {t["accent"]};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QFontComboBox:focus {{
    border: 1px solid {t["accent"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    selection-background-color: {t["selection"]};
    selection-color: {t["text"]};
    outline: none;
}}

/* ---- lists and trees ---- */
QListWidget, QListView, QTreeWidget, QTreeView, QTableView {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_panel"]}px;
    outline: none;
    padding: {t["s1"]}px;
}}
QListWidget::item, QListView::item, QTreeWidget::item, QTreeView::item {{
    padding: {t["s2"]}px;
    border-radius: {t["r_control"]}px;
}}
QListWidget::item:hover, QListView::item:hover, QTreeWidget::item:hover, QTreeView::item:hover {{
    background: {t["hover"]};
}}
QListWidget::item:selected, QListView::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {{
    background: {t["selection"]};
    color: {t["text"]};
}}

/* ---- tabs ---- */
QTabWidget::pane {{
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_panel"]}px;
    background: {t["surface"]};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {t["text2"]};
    border: none;
    padding: {t["s2"]}px {t["s4"]}px;
    min-height: {t["ctl_md"]}px;
}}
QTabBar::tab:hover {{
    color: {t["text"]};
}}
QTabBar::tab:selected {{
    color: {t["text"]};
    border-bottom: 2px solid {t["accent"]};
    font-weight: 600;
}}

/* ---- menus ---- */
QMenu {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_control"]}px;
    padding: {t["s1"]}px;
}}
QMenu::item {{
    padding: {t["s2"]}px {t["s6"]}px {t["s2"]}px {t["s3"]}px;
    border-radius: {t["r_control"]}px;
    min-height: {t["ctl_md"]}px;
}}
QMenu::item:selected {{
    background: {t["hover"]};
}}

/* ---- tooltips ---- */
QToolTip {{
    background: {t["surface"]};
    color: {t["text"]};
    border: 1px solid {t["hairline"]};
    padding: {t["s2"]}px;
    font-size: {t["size_caption"]};
}}

/* ---- scrollbars: quiet 8px ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t["track"]};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t["text4"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t["track"]};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t["text4"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ---- misc ---- */
QProgressBar {{
    background: {t["track"]};
    border: none;
    border-radius: {t["r_pill"]}px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {t["accent"]};
    border-radius: {t["r_pill"]}px;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {t["track"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t["surface"]};
    border: 1px solid {t["hairline"]};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {t["accent"]};
    border-radius: 2px;
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_control"]}px;
    background: {t["surface"]};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {t["accent"]};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {t["accent"]};
    border: 1px solid {t["accent"]};
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: {t["r_control"]}px;
    color: {t["text2"]};
    padding: 3px;
}}
QToolButton:hover {{
    background: {t["hover"]};
    color: {t["text"]};
}}
QToolButton:pressed {{
    background: {t["track"]};
}}
QHeaderView::section {{
    background: {t["surface"]};
    color: {t["text2"]};
    border: none;
    border-bottom: 1px solid {t["hairline"]};
    padding: 6px 8px;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    border: none;
    background: transparent;
    width: 14px;
}}
QGroupBox {{
    border: 1px solid {t["hairline"]};
    border-radius: {t["r_panel"]}px;
    margin-top: 14px;
    padding-top: {t["s2"]}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: {t["text2"]};
}}
QSplitter::handle {{
    background: transparent;
}}
"""


# --------------------------------------------------------------------------
# CSS generation (WebView2 reading overlay)
# --------------------------------------------------------------------------


def css(theme):
    """Generate CSS custom properties + base styles for the overlay HTML page.

    Consumed by htmlcode/uiwebview/mainui.html (injected as a <style> block);
    page-specific selectors stay in the HTML template, values stay here.
    """
    t = theme
    vars_ = "\n".join(f"  --lt-{k}: {_cssv(v)};" for k, v in t.items())
    return f"""/* LunaTranslator Learning UI overlay - generated from designtokens */
:root {{
{vars_}
}}
body {{
  background: transparent;
  color: var(--lt-text);
  font-family: {t["font_ui"]};
  font-size: {t["size_body"]};
}}
.lt-surface {{
  background: {t["overlay_glass"]};
  border: 1px solid var(--lt-hairline);
  border-radius: {t["r_overlay"]}px;
  box-shadow: 0 {t["sh_window"][1]}px {t["sh_window"][0]}px rgba(0, 0, 0, {t["sh_window"][2]});
}}
.lt-hairline {{
  border: none;
  border-top: 1px solid var(--lt-hairline);
}}
.lt-accent {{ color: var(--lt-accent); }}
.lt-secondary {{ color: var(--lt-text2); }}
.lt-status-dot {{
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--lt-live);
}}
.lt-transition {{ transition: all {t["m_default"]}ms {EASE}; }}
@media (prefers-reduced-motion: reduce) {{
  .lt-transition {{ transition: opacity 120ms ease; }}
}}
"""


def _cssv(v):
    """Format a token value for a CSS custom property."""
    if isinstance(v, tuple):
        return " ".join(str(x) for x in v)
    s = str(v)
    if re.match(r"^rgba?\(", s):
        return s
    if s.endswith("px") or s == "999":
        return s
    return s


# --------------------------------------------------------------------------
# helpers for the primitive layer
# --------------------------------------------------------------------------


def shadow_effect(theme, tier):
    """Return (blur, dy, alpha) for a named shadow tier."""
    return theme["sh_" + tier]


def sp(theme, *tokens):
    """Sum spacing tokens, e.g. sp(t, "s2", "s1") -> 12 (as int)."""
    return sum(int(theme[k]) for k in tokens)
