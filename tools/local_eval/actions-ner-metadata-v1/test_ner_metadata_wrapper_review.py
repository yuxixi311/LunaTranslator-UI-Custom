"""Prepared offline wrapper tests; fake timeout never launches the collector."""

import hashlib
import pathlib
import re
import shlex
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
WRAPPER_TEXT = (ROOT / "ner_metadata_job_wrapper_review.sh").read_text()


class WrapperReviewTests(unittest.TestCase):
    def fake_run(self, exit_code=0, stdout='{"status":"metadata_reads_complete"}', release=True, correct_hash=True):
        with tempfile.TemporaryDirectory(prefix="metadata-wrapper-fake-") as temporary:
            directory = pathlib.Path(temporary)
            # This inert file is hash checked but never executed.
            collector = directory / "ner_metadata_fetcher_review.py"
            collector.write_text("# inert offline fixture\n")
            expected = hashlib.sha256(collector.read_bytes()).hexdigest() if correct_hash else "0" * 64
            timeout = directory / "fake-timeout"
            args_path = directory / "arguments.txt"
            timeout.write_text("#!/bin/sh\n" +
                               "printf '%s\\n' \"$@\" > " + shlex.quote(str(args_path)) + "\n" +
                               "printf '%s' " + shlex.quote(stdout) + "\n" +
                               "printf '%s' 'secret-stderr-canary' >&2\n" +
                               "exit " + str(exit_code) + "\n")
            timeout.chmod(0o700)
            text = re.sub(r"^SOURCE_ONLY=[01]$", "SOURCE_ONLY=0" if release else "SOURCE_ONLY=1", WRAPPER_TEXT, flags=re.MULTILINE)
            text = re.sub(r"^EXPECTED_SOURCE_SHA256=.*$", "EXPECTED_SOURCE_SHA256=" + expected, text, flags=re.MULTILINE)
            text = text.replace("TIMEOUT_BIN=/usr/bin/timeout", "TIMEOUT_BIN=" + shlex.quote(str(timeout)))
            wrapper = directory / "wrapper.sh"
            wrapper.write_text(text)
            result = subprocess.run(["/bin/sh", str(wrapper)], capture_output=True, text=True, timeout=5)
            arguments = args_path.read_text().splitlines() if args_path.exists() else []
            self.assertNotIn("secret-stderr-canary", result.stdout + result.stderr)
            return result, arguments

    def test_template_stays_disabled(self):
        result, arguments = self.fake_run(release=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('"code":"source_only_disabled"', result.stdout)
        self.assertEqual(arguments, [])

    def test_hash_mismatch_never_starts_owned_process(self):
        result, arguments = self.fake_run(correct_hash=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn('"code":"source_hash_mismatch"', result.stdout)
        self.assertEqual(arguments, [])

    def test_success_is_public_receipt_and_exact_timeout_contract(self):
        result, arguments = self.fake_run()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{"status":"metadata_reads_complete"}\n')
        self.assertEqual(arguments[:6], ["--signal=TERM", "--kill-after=5s", "55s", "python3", "-I", "-B"])

    def test_clean_metadata_failure_is_preserved(self):
        receipt = '{"status":"blocked","code":"transport_failure","attempted_gets":1}'
        result, unused = self.fake_run(exit_code=2, stdout=receipt)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, receipt + "\n")

    def test_timeout_or_kill_is_finite(self):
        for code in (124, 137, 143):
            with self.subTest(code=code):
                result, unused = self.fake_run(exit_code=code, stdout="partial-untrusted-text")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '{"status":"blocked","code":"process_deadline"}\n')

    def test_cancellation_is_finite(self):
        result, unused = self.fake_run(exit_code=130, stdout="partial-untrusted-text")
        self.assertEqual(result.stdout, '{"status":"blocked","code":"cancelled"}\n')

    def test_unexpected_process_failure_is_finite(self):
        result, unused = self.fake_run(exit_code=1, stdout="partial-untrusted-text")
        self.assertEqual(result.stdout, '{"status":"blocked","code":"process_failure"}\n')

    def test_output_cap_is_finite(self):
        result, unused = self.fake_run(stdout="{" + "x" * 65536 + "}")
        self.assertEqual(result.stdout, '{"status":"blocked","code":"output_limit"}\n')

    def test_missing_receipt_is_finite(self):
        result, unused = self.fake_run(stdout="")
        self.assertEqual(result.stdout, '{"status":"blocked","code":"missing_public_receipt"}\n')


if __name__ == "__main__":
    unittest.main()
