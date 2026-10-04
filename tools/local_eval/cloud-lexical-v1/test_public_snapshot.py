"""Packaging verification only; no real package or analyzer execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pilot_runner as runner


class PublicSnapshotTests(unittest.TestCase):
    def test_public_source_inventory(self):
        manifest = runner.read_json(runner.ROOT / 'PUBLIC_SOURCE_MANIFEST.json')
        self.assertEqual(manifest['status'], 'NOT EXECUTED')
        self.assertFalse(manifest['execution_manifest_included'])
        for name, expected in manifest['files'].items():
            self.assertFalse(Path(name).is_absolute())
            self.assertNotIn('..', Path(name).parts)
            runner.verify_file(runner.ROOT / name, expected)

    def test_freeze_uses_only_public_manifest_names(self):
        # Copy pinned source bytes to a disposable directory and freeze there.
        # No download, setup, parser or real process launch is called.
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = runner.read_json(runner.ROOT / 'PUBLIC_SOURCE_MANIFEST.json')
            for name in manifest['files']:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(runner.ROOT / name, destination)
            with patch.object(runner, 'ROOT', root):
                runner.freeze()
                public = root / 'PUBLIC_EXECUTION_MANIFEST.json'
                self.assertTrue(public.is_file())
                self.assertFalse((root / 'EXECUTION_MANIFEST.json').exists())
                self.assertEqual(runner.verify_manifest(runner.digest_file(public)['sha256'])['planned_calls'], 48)


if __name__ == '__main__':
    unittest.main()
