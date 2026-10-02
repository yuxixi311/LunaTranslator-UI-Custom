"""Headless download tests; only tiny synthetic files, never model downloads."""

import hashlib
import http.client
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import urllib.request


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "LunaTranslator"))
from myutils import local_model_download as models


class FakeResponse(io.BytesIO):
    def __init__(self, data, status=200, headers=None, url="https://cdn.example/model.gguf"):
        super().__init__(data)
        self.status = status
        self.headers = {} if headers is None else headers
        self.url = url

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status

    def read1(self, size=-1):
        return self.read(size)


class CatalogTests(unittest.TestCase):
    def test_catalog_pins_official_lfs_objects_and_order(self):
        expected = [
            (
                "hymt2-1.8b-q4", "Hy-MT2-1.8B-Q4_K_M.gguf", "tencent/Hy-MT2-1.8B-GGUF",
                "b27182d810fa3ceb6ed04e7c324c54e35c0d209c", 1133080448,
                "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
            ),
            (
                "hymt2-7b-q4", "Hy-MT2-7B-Q4_K_M.gguf", "tencent/Hy-MT2-7B-GGUF",
                "707464294cf5b2a5a69982855020858ed58cf1d1", 4624648896,
                "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b",
            ),
        ]
        self.assertEqual(list(models.MODEL_PRESETS), [row[0] for row in expected])
        for key, filename, repo, revision, size, sha256 in expected:
            value = models.MODEL_PRESETS[key]
            self.assertEqual(value["filename"], filename)
            self.assertEqual(value["repo"], repo)
            self.assertEqual(value["revision"], revision)
            self.assertEqual(value["size"], size)
            self.assertEqual(value["sha256"], sha256)
            self.assertTrue(value["title"])
            self.assertEqual(
                value["license_url"],
                "https://huggingface.co/{}/blob/{}/LICENSE.txt".format(
                    repo.removesuffix("-GGUF"),
                    "9a341cd1b679d3efd23b46e847b01745a71ed792" if key == "hymt2-1.8b-q4" else "9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223",
                ),
            )


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.data = b"GGUF\x03\x00\x00\x00synthetic test model bytes"
        self.preset = {
            "title": "Synthetic fixture only",
            "filename": "fixture.gguf",
            "repo": "test/synthetic",
            "revision": "a" * 40,
            "size": len(self.data),
            "sha256": hashlib.sha256(self.data).hexdigest(),
            "license_url": "https://example.test/LICENSE",
        }
        self.key = "fixture"
        self.destination = self.directory / self.preset["filename"]
        patch = mock.patch.dict(models.MODEL_PRESETS, {self.key: self.preset}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(models, "_CHUNK_SIZE", 8)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(
            models.shutil, "disk_usage", return_value=SimpleNamespace(free=100000000)
        )
        self.disk_usage = patch.start()
        self.addCleanup(patch.stop)

    def assert_no_partials(self):
        self.assertEqual(list(self.directory.glob("*.part")), [])

    def fetch(self, response=None, **kwargs):
        if response is None:
            response = FakeResponse(self.data)
        opener = mock.Mock(return_value=response)
        path = models.download_model(self.key, self.directory, opener=opener, **kwargs)
        return path, response, opener

    def test_valid_download_pins_url_verifies_fsyncs_closes_and_installs(self):
        updates = []
        response = FakeResponse(self.data, headers={"Content-Length": str(len(self.data))})
        original_replace = os.replace

        def checked_replace(source, destination):
            self.assertTrue(response.closed)
            self.assertEqual(Path(source).parent, self.directory)
            self.assertEqual(Path(source).read_bytes(), self.data)
            original_replace(source, destination)

        with mock.patch.object(models.os, "fsync", wraps=os.fsync) as fsync, mock.patch.object(
            models.os, "replace", side_effect=checked_replace
        ) as replace:
            path, response, opener = self.fetch(
                response, progress=lambda done, total: updates.append((done, total))
            )
        self.assertEqual(path, self.destination)
        self.assertEqual(path.read_bytes(), self.data)
        self.assertTrue(response.closed)
        self.assertEqual(fsync.call_count, 1)
        self.assertEqual(replace.call_count, 1)
        request = opener.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://huggingface.co/test/synthetic/resolve/{}/fixture.gguf".format("a" * 40),
        )
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertEqual(opener.call_args.kwargs["timeout"], models.HTTP_TIMEOUT_SECONDS)
        self.assertEqual(updates[0], (0, len(self.data)))
        self.assertEqual(updates[-1], (len(self.data), len(self.data)))
        self.assertEqual(updates, sorted(updates))
        self.assert_no_partials()

    def test_opener_object_and_metadata_dictionary_supported(self):
        opener = SimpleNamespace(open=mock.Mock(return_value=FakeResponse(self.data)))
        result = models.download_model(dict(self.preset), self.directory, opener=opener)
        self.assertEqual(result.read_bytes(), self.data)
        opener.open.assert_called_once()

    def test_default_opener_installs_https_redirect_guard(self):
        opener = SimpleNamespace(open=mock.Mock(return_value=FakeResponse(self.data)))
        with mock.patch.object(models.urllib.request, "build_opener", return_value=opener) as build:
            models.download_model(self.key, self.directory)
        self.assertIsInstance(build.call_args.args[0], models._HTTPSRedirectHandler)

    def test_existing_verified_file_skips_network_disk_requirement_and_replace(self):
        self.destination.write_bytes(self.data)
        self.disk_usage.return_value.free = 0
        opener = mock.Mock(side_effect=AssertionError("must not open network"))
        with mock.patch.object(models.os, "replace") as replace:
            result = models.download_model(self.key, self.directory, opener=opener)
        self.assertEqual(result, self.destination)
        opener.assert_not_called()
        self.disk_usage.assert_not_called()
        replace.assert_not_called()
        self.assert_no_partials()

    def test_invalid_existing_file_is_replaced_only_on_success(self):
        self.destination.write_bytes(b"old invalid model")
        original_replace = os.replace

        def checked_replace(source, destination):
            self.assertEqual(self.destination.read_bytes(), b"old invalid model")
            self.assertEqual(Path(source).read_bytes(), self.data)
            original_replace(source, destination)

        with mock.patch.object(models.os, "replace", side_effect=checked_replace):
            result, _, _ = self.fetch()
        self.assertEqual(result.read_bytes(), self.data)
        self.assert_no_partials()

    def test_corrupt_download_preserves_existing_and_retry_succeeds(self):
        old = b"old invalid model"
        self.destination.write_bytes(old)
        response = FakeResponse(b"x" * len(self.data))
        with self.assertRaisesRegex(models.ModelDownloadError, "SHA-256"):
            self.fetch(response)
        self.assertEqual(self.destination.read_bytes(), old)
        self.assertTrue(response.closed)
        self.assert_no_partials()
        self.fetch()
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assert_no_partials()

    def test_truncated_response_is_not_installed_and_can_retry(self):
        response = FakeResponse(self.data[:-1])
        with self.assertRaisesRegex(models.ModelDownloadError, "size mismatch"):
            self.fetch(response)
        self.assertTrue(response.closed)
        self.assertFalse(self.destination.exists())
        self.assert_no_partials()
        self.fetch()
        self.assertEqual(self.destination.read_bytes(), self.data)

    def test_oversized_response_is_stopped_before_extra_bytes_are_written(self):
        response = FakeResponse(self.data + b"extra")
        with self.assertRaisesRegex(models.ModelDownloadError, "exceeded"):
            self.fetch(response)
        self.assertTrue(response.closed)
        self.assertFalse(self.destination.exists())
        self.assert_no_partials()

    def test_bad_status_headers_encoding_and_final_url_close_response(self):
        cases = [
            ({"status": 403}, "HTTP 403"),
            ({"status": 206}, "HTTP 206"),
            ({"headers": {"Content-Length": "3"}}, "size mismatch"),
            ({"headers": {"Content-Length": "invalid"}}, "Content-Length"),
            ({"headers": {"Content-Length": "-1"}}, "size mismatch"),
            ({"headers": {"Content-Encoding": "gzip"}}, "encoding"),
            ({"url": "http://cdn.example/model.gguf"}, "HTTPS"),
            ({"url": "https://name:password@cdn.example/model.gguf"}, "HTTPS"),
        ]
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs):
                response = FakeResponse(self.data, **kwargs)
                with self.assertRaisesRegex(models.ModelDownloadError, message):
                    self.fetch(response)
                self.assertTrue(response.closed)
                self.assertFalse(self.destination.exists())
                self.assert_no_partials()

    def test_http_error_response_is_closed(self):
        response = FakeResponse(b"Forbidden")
        error = urllib.error.HTTPError("https://example.test", 403, "Forbidden", {}, response)
        with self.assertRaisesRegex(models.ModelDownloadError, "HTTP 403"):
            models.download_model(
                self.key, self.directory, opener=mock.Mock(side_effect=error)
            )
        self.assertTrue(response.closed)
        self.assert_no_partials()

    def test_timeout_and_connection_error_are_clear_and_retryable(self):
        for error in (TimeoutError("timed out"), urllib.error.URLError("offline")):
            with self.subTest(error=error):
                with self.assertRaisesRegex(models.ModelDownloadError, "Retry"):
                    models.download_model(
                        self.key, self.directory, opener=mock.Mock(side_effect=error)
                    )
                self.assert_no_partials()
        self.fetch()

    def test_read_error_closes_response_cleans_partial_and_preserves_existing(self):
        self.destination.write_bytes(b"old file")
        response = FakeResponse(self.data)
        response.read = mock.Mock(side_effect=[self.data[:8], OSError("connection lost")])
        with self.assertRaisesRegex(models.ModelDownloadError, "connection lost"):
            self.fetch(response)
        self.assertTrue(response.closed)
        self.assertEqual(self.destination.read_bytes(), b"old file")
        self.assert_no_partials()

    def test_response_read1_is_preferred_over_block_filling_read(self):
        response = FakeResponse(self.data)
        response.read = mock.Mock(side_effect=AssertionError("must prefer read1"))
        response.read1 = mock.Mock(side_effect=lambda size: io.BytesIO.read(response, size))
        path, _, _ = self.fetch(response)
        self.assertEqual(path.read_bytes(), self.data)
        self.assertGreater(response.read1.call_count, 1)
        response.read1.assert_called_with(models._CHUNK_SIZE)
        response.read.assert_not_called()
        self.assertTrue(response.closed)
        self.assert_no_partials()

    def test_cancel_after_first_short_read1_does_not_wait_to_fill_chunk(self):
        self.destination.write_bytes(b"old file")
        state = {"cancelled": False}
        updates = []
        response = FakeResponse(self.data)
        response.read = mock.Mock(side_effect=AssertionError("must prefer read1"))
        response.read1 = mock.Mock(side_effect=[self.data[:1], AssertionError("must cancel before next read")])

        def progress(done, total):
            updates.append((done, total))
            state["cancelled"] = done > 0

        with self.assertRaises(models.CancelledDownload):
            self.fetch(response, progress=progress, cancelled=lambda: state["cancelled"])
        response.read1.assert_called_once_with(models._CHUNK_SIZE)
        response.read.assert_not_called()
        self.assertEqual(updates, [(0, len(self.data)), (1, len(self.data))])
        self.assertTrue(response.closed)
        self.assertEqual(self.destination.read_bytes(), b"old file")
        self.assert_no_partials()

    def test_response_without_read1_uses_read_fallback(self):
        buffer = FakeResponse(self.data)
        response = SimpleNamespace(
            headers=buffer.headers,
            geturl=buffer.geturl,
            getcode=buffer.getcode,
            read=mock.Mock(wraps=buffer.read),
            close=buffer.close,
        )
        path, _, _ = self.fetch(response)
        self.assertEqual(path.read_bytes(), self.data)
        response.read.assert_called_with(models._CHUNK_SIZE)
        self.assertTrue(buffer.closed)
        self.assert_no_partials()

    def test_incomplete_http_read_closes_response_and_cleans_partial(self):
        response = FakeResponse(self.data)
        response.read = mock.Mock(side_effect=http.client.IncompleteRead(b"GGUF", 30))
        with self.assertRaisesRegex(models.ModelDownloadError, "Retry"):
            self.fetch(response)
        self.assertTrue(response.closed)
        self.assertFalse(self.destination.exists())
        self.assert_no_partials()

    def test_progress_callback_error_also_closes_and_cleans_partial(self):
        response = FakeResponse(self.data)
        with self.assertRaisesRegex(RuntimeError, "callback"):
            self.fetch(response, progress=mock.Mock(side_effect=RuntimeError("callback")))
        self.assertTrue(response.closed)
        self.assertFalse(self.destination.exists())
        self.assert_no_partials()

    def test_tempfile_creation_error_closes_response(self):
        response = FakeResponse(self.data)
        with mock.patch.object(models.tempfile, "NamedTemporaryFile", side_effect=OSError("permission denied")):
            with self.assertRaisesRegex(models.ModelDownloadError, "permission denied"):
                self.fetch(response)
        self.assertTrue(response.closed)
        self.assertFalse(self.destination.exists())
        self.assert_no_partials()

    def test_insufficient_disk_space_fails_before_network(self):
        self.destination.write_bytes(b"old file")
        self.disk_usage.return_value.free = len(self.data) + models._DISK_RESERVE_BYTES - 1
        opener = mock.Mock(side_effect=AssertionError("must not open network"))
        with self.assertRaisesRegex(models.ModelDownloadError, "free disk space"):
            models.download_model(self.key, self.directory, opener=opener)
        opener.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), b"old file")
        self.assert_no_partials()

    def test_cancel_before_download_does_not_create_directory_or_open_network(self):
        directory = self.directory / "not-created"
        opener = mock.Mock(side_effect=AssertionError("must not open network"))
        with self.assertRaises(models.CancelledDownload):
            models.download_model(self.key, directory, cancelled=lambda: True, opener=opener)
        self.assertFalse(directory.exists())
        opener.assert_not_called()

    def test_cancel_during_download_cleans_partial_and_preserves_existing(self):
        self.destination.write_bytes(b"old file")
        state = {"cancelled": False}

        def progress(done, total):
            state["cancelled"] = done >= 8

        response = FakeResponse(self.data)
        with self.assertRaises(models.CancelledDownload):
            self.fetch(response, progress=progress, cancelled=lambda: state["cancelled"])
        self.assertTrue(response.closed)
        self.assertEqual(self.destination.read_bytes(), b"old file")
        self.assert_no_partials()

    def test_cancel_verifying_existing_file_never_starts_download(self):
        self.destination.write_bytes(self.data)
        state = {"cancelled": False}

        def progress(done, total):
            state["cancelled"] = done >= 8

        opener = mock.Mock()
        with self.assertRaises(models.CancelledDownload):
            models.download_model(
                self.key, self.directory, opener=opener,
                cancelled=lambda: state["cancelled"], progress=progress,
            )
        opener.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assert_no_partials()

    def test_cancel_after_fsync_before_install_keeps_existing_file(self):
        self.destination.write_bytes(b"old file")
        state = {"cancelled": False}
        response = FakeResponse(self.data)

        def cancel_after_fsync(fd):
            state["cancelled"] = True

        with mock.patch.object(models.os, "fsync", side_effect=cancel_after_fsync), mock.patch.object(
            models.os, "replace"
        ) as replace:
            with self.assertRaises(models.CancelledDownload):
                self.fetch(response, cancelled=lambda: state["cancelled"])
        replace.assert_not_called()
        self.assertTrue(response.closed)
        self.assertEqual(self.destination.read_bytes(), b"old file")
        self.assert_no_partials()

    def test_fsync_and_replace_errors_clean_partial_and_preserve_existing(self):
        self.destination.write_bytes(b"old file")
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                response = FakeResponse(self.data)
                with mock.patch.object(models.os, operation, side_effect=OSError("disk failure")):
                    with self.assertRaisesRegex(models.ModelDownloadError, "disk failure"):
                        self.fetch(response)
                self.assertTrue(response.closed)
                self.assertEqual(self.destination.read_bytes(), b"old file")
                self.assert_no_partials()

    def test_only_own_unique_partial_is_removed_on_error(self):
        unrelated = self.directory / ".fixture.gguf.other-attempt.part"
        unrelated.write_bytes(b"other attempt")
        partial_names = []

        def progress(done, total):
            partial_names.extend(self.directory.glob("*.part"))

        for _ in range(2):
            with self.assertRaises(models.ModelDownloadError):
                self.fetch(FakeResponse(b"x" * len(self.data)), progress=progress)
        names = set(partial_names) - {unrelated}
        self.assertEqual(len(names), 2)
        self.assertEqual(list(self.directory.glob("*.part")), [unrelated])
        self.assertEqual(unrelated.read_bytes(), b"other attempt")

    def test_unknown_preset_and_modified_metadata_are_rejected_without_network(self):
        for preset in ("unknown", {**self.preset, "sha256": "0" * 64}, None):
            with self.subTest(preset=preset):
                opener = mock.Mock()
                with self.assertRaisesRegex(models.ModelDownloadError, "supported"):
                    models.download_model(preset, self.directory, opener=opener)
                opener.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_invalid_catalog_paths_are_rejected(self):
        for filename in ("../escape.gguf", "..\\escape.gguf", "/absolute.gguf"):
            with self.subTest(filename=filename), mock.patch.dict(self.preset, {"filename": filename}):
                with self.assertRaisesRegex(models.ModelDownloadError, "metadata"):
                    models.download_model(self.key, self.directory, opener=mock.Mock())

    def test_directory_destination_fails_without_network(self):
        self.destination.mkdir()
        opener = mock.Mock()
        with self.assertRaisesRegex(models.ModelDownloadError, "regular file"):
            models.download_model(self.key, self.directory, opener=opener)
        opener.assert_not_called()

    def test_verify_accepts_exact_model_without_modification(self):
        manual = self.directory / "renamed.gguf"
        manual.write_bytes(self.data)
        before = manual.stat().st_mtime_ns
        updates = []
        result = models.verify_model(
            manual, self.key, progress=lambda done, total: updates.append((done, total))
        )
        self.assertEqual(result, manual)
        self.assertEqual(manual.read_bytes(), self.data)
        self.assertEqual(manual.stat().st_mtime_ns, before)
        self.assertEqual(updates[-1], (len(self.data), len(self.data)))
        self.assertEqual(list(self.directory.iterdir()), [manual])

    def test_verify_rejects_unknown_gguf_corruption_size_and_missing_file(self):
        for data, message in ((b"GGUF arbitrary model", "size mismatch"), (b"x" * len(self.data), "SHA-256")):
            with self.subTest(message=message):
                self.destination.write_bytes(data)
                with self.assertRaisesRegex(models.ModelDownloadError, message):
                    models.verify_model(self.destination, self.key)
                self.assertEqual(self.destination.read_bytes(), data)
        with self.assertRaises(models.ModelDownloadError):
            models.verify_model(self.directory / "missing.gguf", self.key)

    def test_verify_cancelled_midway_and_before_return(self):
        self.destination.write_bytes(self.data)
        for threshold in (8, len(self.data)):
            with self.subTest(threshold=threshold):
                state = {"cancelled": False}

                def progress(done, total):
                    state["cancelled"] = done >= threshold

                with self.assertRaises(models.CancelledDownload):
                    models.verify_model(
                        self.destination, self.key,
                        cancelled=lambda: state["cancelled"], progress=progress,
                    )
                self.assertEqual(self.destination.read_bytes(), self.data)

    def test_verification_detects_file_changed_while_hashing(self):
        self.destination.write_bytes(self.data)

        def progress(done, total):
            if done == total:
                self.destination.write_bytes(b"x" * len(self.data))
                current = self.destination.stat()
                os.utime(self.destination, ns=(current.st_atime_ns, current.st_mtime_ns + 1000000000))

        with self.assertRaisesRegex(models.ModelDownloadError, "changed"):
            models.verify_model(self.destination, self.key, progress=progress)


class RedirectTests(unittest.TestCase):
    def test_downgrade_and_non_https_redirects_are_rejected_before_following(self):
        handler = models._HTTPSRedirectHandler()
        for target in ("http://example.test/file", "ftp://example.test/file", "file:///tmp/file"):
            with self.subTest(target=target):
                response = FakeResponse(b"")
                with self.assertRaisesRegex(models.ModelDownloadError, "HTTPS"):
                    handler.redirect_request(
                        urllib.request.Request("https://huggingface.co/test"),
                        response, 302, "Found", {}, target,
                    )
                self.assertTrue(response.closed)

    def test_https_cdn_redirect_is_supported(self):
        request = models._HTTPSRedirectHandler().redirect_request(
            urllib.request.Request("https://huggingface.co/test"),
            FakeResponse(b""), 302, "Found", {}, "https://cdn.example.test/file",
        )
        self.assertEqual(request.full_url, "https://cdn.example.test/file")


if __name__ == "__main__":
    unittest.main()
