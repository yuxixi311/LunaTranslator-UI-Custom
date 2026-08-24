"""Tests for gui.ltwidgets primitives - offscreen render + property checks.
Run: python src/tests/test_ltwidgets.py"""

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "LunaTranslator"))

from qtsymbols import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame

app = QApplication([])
artifacts = tempfile.TemporaryDirectory(prefix="luna-translate-ui-tests-")
light_render = os.path.join(artifacts.name, "primitives-light.png")
dark_render = os.path.join(artifacts.name, "primitives-dark.png")

# force light/dark by monkeypatching the resolver used by ltwidgets
import gui.ltwidgets as ltw
from myutils.designtokens import LIGHT, DARK

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


# --- build one of each primitive ---
def build_page():
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setSpacing(8)

    row1 = QHBoxLayout()
    row1.addWidget(ltw.LtButton("Primary", variant="primary"))
    row1.addWidget(ltw.LtButton("Secondary"))
    row1.addWidget(ltw.LtButton("Quiet", variant="quiet"))
    row1.addWidget(ltw.LtButton("Danger", variant="danger"))
    lay.addLayout(row1)

    lay.addWidget(ltw.LtSegmented([("compact", "Compact"), ("expanded", "Expanded")], current="compact"))
    lay.addWidget(ltw.LtLineEdit(placeholder="Enter text..."))
    lay.addWidget(ltw.LtComboBox(["Option A", "Option B"]))
    lay.addWidget(ltw.LtHairline())

    panel = ltw.LtPanelList()
    panel.add_row(title="OCR engine", subtitle="Windows OCR", control=ltw.LtComboBox(["Windows OCR"]))
    panel.add_row(title="Japanese font", subtitle="Yu Gothic UI", control=ltw.LtLineEdit())
    panel.add_row(title="Furigana visibility", control=ltw.LtSegmented([("on", "On"), ("off", "Off")], current="on"))
    lay.addWidget(panel)

    dotrow = QHBoxLayout()
    dotrow.addWidget(ltw.LtStatusDot())
    lay.addLayout(dotrow)
    return page


def render(page, path):
    page.resize(560, 420)
    page.show()
    app.processEvents()
    pm = page.grab()
    pm.save(path)
    return pm


# --- light theme ---
ltw.lt_isdark = lambda: False
ltw.lt_tokens = lambda: LIGHT
page_l = build_page()
render(page_l, light_render)

# --- dark theme ---
ltw.lt_isdark = lambda: True
ltw.lt_tokens = lambda: DARK
page_d = build_page()
render(page_d, dark_render)

# --- assertions ---
check("light render non-empty", os.path.getsize(light_render) > 2000)
check("dark render non-empty", os.path.getsize(dark_render) > 2000)
check("primary button ltClass", ltw.LtButton("x", variant="primary").property("ltClass") == "primary")
check("quiet button ltClass", ltw.LtButton("x", variant="quiet").property("ltClass") == "quiet")
check("panel glass ltClass", ltw.LtPanel().property("ltClass") == "glass")

seg = ltw.LtSegmented([("a", "A"), ("b", "B")], current="a")
check("segmented current", seg.current() == "a")
seg._select("b", emit=True)
check("segmented switch", seg.current() == "b")

dot = ltw.LtStatusDot()
check("status dot 7px", dot.width() == 7 and dot.height() == 7)
dot.set_live(False)

panel_list = ltw.LtPanelList()
panel_list.add_row(title="t1")
panel_list.add_row(title="t2")
check("panel list rows", len(panel_list._rows) == 2)
check("panel list hairline on first row", "border-bottom" in panel_list._rows[0].styleSheet())
check("panel list no hairline on last row", "border-bottom" not in panel_list._rows[1].styleSheet())

print()
print("RESULT:", "ALL PASS" if not failures else f"FAILURES: {failures}")
artifacts.cleanup()
sys.exit(0 if not failures else 1)
