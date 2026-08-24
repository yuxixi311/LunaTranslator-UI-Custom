import ast
import json
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "LunaTranslator")


def read_source(*parts):
    path = os.path.join(APP, *parts)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class JapaneseReadShortcutTests(unittest.TestCase):
    def test_default_toolbar_exposes_japanese_read_button(self):
        config = json.loads(read_source("defaultconfig", "config.json"))
        button = config["toolbutton"]["buttons"]["langdu"]

        self.assertGreaterEqual(config["learning_ui_feature_revision"], 5)
        self.assertTrue(button["use"])
        self.assertEqual(button["tip"], "朗读当前日文（右键暂停/继续）")
        self.assertEqual(button["icon"], "fa.volume-up")
        self.assertEqual(
            config["toolbutton"]["rank2"][-3:],
            ["showtrans", "langdu", "ttsrate"],
        )

    def test_existing_compact_configs_get_one_time_button_migration(self):
        config_source = read_source("myutils", "config.py")

        self.assertIn("_learning_ui_feature_revision_before_sync < 2", config_source)
        self.assertIn(
            'globalconfig["toolbutton"]["buttons"]["langdu"]["use"] = True',
            config_source,
        )
        self.assertIn("_learning_ui_feature_revision_before_sync < 3", config_source)
        self.assertIn(
            'toolbar_rank.extend(("showtrans", "langdu"))', config_source
        )
        self.assertIn("_learning_ui_feature_revision_before_sync < 4", config_source)
        self.assertIn(
            'globalconfig["reader"]["edgetts"]["voice"] = '
            '"ja-JP-NanamiNeural"',
            config_source,
        )
        self.assertIn(
            'globalconfig["learning_ui_feature_revision"] = defaultglobalconfig[',
            config_source,
        )
        self.assertIn("_learning_ui_feature_revision_before_sync < 5", config_source)
        self.assertIn(
            'toolbar_rank.extend(("showtrans", "langdu", "ttsrate"))',
            config_source,
        )

    def test_simplified_toolbar_keeps_japanese_read_button(self):
        module = ast.parse(read_source("gui", "translatorUI.py"))
        translator_window = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "TranslatorWindow"
        )
        assignment = next(
            node
            for node in translator_window.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "SIMPLIFIED_BUTTONS"
                for target in node.targets
            )
        )
        values = {item.value for item in assignment.value.elts}

        self.assertIn("langdu", values)
        self.assertIn("ttsrate", values)

    def test_toolbar_and_global_hotkey_force_original_text(self):
        translator_ui = read_source("gui", "translatorUI.py")
        hotkey = read_source("gui", "setting", "hotkey.py")
        expected = "readcurrent(force=True,origin_only=True)"

        self.assertIn(expected, "".join(translator_ui.split()))
        self.assertIn(expected, "".join(hotkey.split()))
        self.assertIn("audioplayer.toggle_pause()", translator_ui)
        self.assertIn('"ttsrate"', translator_ui)
        self.assertIn("textstate=self.currentTtsSpeedLabel", translator_ui)

    def test_origin_only_path_selects_current_source_text(self):
        module = ast.parse(read_source("LunaTranslator.py"))
        base_object = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "BASEOBJECT"
        )
        readcurrent = next(
            node
            for node in base_object.body
            if isinstance(node, ast.FunctionDef) and node.name == "readcurrent"
        )
        text_assignment = next(
            node
            for node in readcurrent.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "text1"
                for target in node.targets
            )
        )

        self.assertEqual(
            ast.unparse(text_assignment.value),
            "self.currenttext if origin_only else self.currentread",
        )

    def test_hotkey_label_describes_japanese_text(self):
        config = json.loads(read_source("defaultconfig", "config.json"))

        self.assertEqual(
            config["quick_setting"]["all"]["_7"]["name"], "朗读当前日文"
        )

    def test_nanami_is_default_and_keita_remains_selectable(self):
        config = json.loads(read_source("defaultconfig", "config.json"))
        quick = read_source("gui", "setting", "quick.py")

        self.assertTrue(config["reader"]["edgetts"]["use"])
        self.assertFalse(config["reader"]["windowstts"]["use"])
        self.assertEqual(
            config["reader"]["edgetts"]["voice"], "ja-JP-NanamiNeural"
        )
        self.assertIn("日语朗读音色", quick)
        self.assertIn("ja-JP-NanamiNeural", quick)
        self.assertIn("ja-JP-KeitaNeural", quick)

    def test_voice_selector_shows_complete_voice_names(self):
        quick = read_source("gui", "setting", "quick.py")

        self.assertIn("Nanami　·　自然女声（默认）", quick)
        self.assertIn("Keita　·　自然男声", quick)
        self.assertIn("默认音色：Nanami　 · 　在线自然发音", quick)
        self.assertIn("AdjustToContents", quick)
        self.assertIn("setMinimumWidth(full_width)", quick)
        self.assertIn("Qt.TextElideMode.ElideNone", quick)


if __name__ == "__main__":
    unittest.main()
