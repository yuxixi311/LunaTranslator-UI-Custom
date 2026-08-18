"""Tests for myutils.designtokens - run: python src/tests/test_designtokens.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "LunaTranslator"))

from myutils.designtokens import LIGHT, DARK, EASE, css, qss, resolve_theme

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)


# 1. light/dark share the exact key set
check("key sets identical", set(LIGHT) == set(DARK))

# 2. resolve_theme
check("resolve_theme(True) is DARK", resolve_theme(True) is DARK)
check("resolve_theme(False) is LIGHT", resolve_theme(False) is LIGHT)

# 3. qss generates for both themes and carries theme-distinct values
ql = qss(LIGHT)
qd = qss(DARK)
check("qss light generates", isinstance(ql, str) and len(ql) > 1000)
check("qss dark generates", isinstance(qd, str) and len(qd) > 1000)
check("qss light uses light bg", LIGHT["bg"] in ql)
check("qss dark uses dark bg", DARK["bg"] in qd)
check("qss light has no dark bg", DARK["bg"] not in ql)
# dark TEXT equals light BG by design (charter values), so assert on background usage
check("qss dark never uses light bg as background", f"background: {LIGHT['bg']}" not in qd)
check("qss light uses light accent", LIGHT["accent"] in ql)
check("qss dark uses dark accent", DARK["accent"] in qd)
check("qss has hairline divider", LIGHT["hairline"] in ql)
check("qss radii from tokens", f"{LIGHT['r_panel']}px" in ql and f"{LIGHT['r_overlay']}px" not in ql)

# 4. css generates with :root variables
cl = css(LIGHT)
cd = css(DARK)
check("css light generates", ":root" in cl and "--lt-accent" in cl)
check("css dark generates", ":root" in cd and "--lt-accent" in cd)
check("css light accent var", LIGHT["accent"] in cl)
check("css dark accent var", DARK["accent"] in cd)
check("css surface class present", ".lt-surface" in cl)
check("css reduced-motion media query", "prefers-reduced-motion" in cl)

# 5. accents differ between themes (no same-theme accident)
check("accents differ", LIGHT["accent"] != DARK["accent"])
check("bgs differ", LIGHT["bg"] != DARK["bg"])

# 6. easing token
check("easing defined", EASE.startswith("cubic-bezier"))

# 7. typography: system fonts only, no Apple fonts
check("no SF/Apple fonts in ui stack", "SF Pro" not in LIGHT["font_ui"] and "PingFang" not in LIGHT["font_ui"])
check("segoe present in ui stack", "Segoe UI" in LIGHT["font_ui"])
check("japanese font present", "Yu Gothic UI" in LIGHT["font_jp"])

print()
print("RESULT:", "ALL PASS" if not failures else f"FAILURES: {failures}")
sys.exit(0 if not failures else 1)
