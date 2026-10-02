"""Verified, cancellable downloads for the two supported offline GGUF presets.

This module deliberately imports no Qt/application code. It only accepts a
registered preset, including for manual imports: a GGUF extension alone is not
evidence that an arbitrary model is compatible. Model metadata is pinned to the
official Hugging Face Git LFS objects, whose SHA-256 is the hash of the actual
file (not the Xet storage identifier).
"""

from collections import OrderedDict
from collections.abc import Mapping
from contextlib import closing
import hashlib
import http.client
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request


MODEL_PRESETS = OrderedDict(
    (
        (
            "hymt2-1.8b-q4",
            {
                "title": "Hy-MT2 1.8B Q4_K_M",
                "filename": "Hy-MT2-1.8B-Q4_K_M.gguf",
                "repo": "tencent/Hy-MT2-1.8B-GGUF",
                "revision": "b27182d810fa3ceb6ed04e7c324c54e35c0d209c",
                "size": 1133080448,
                "sha256": "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699",
                "license_url": "https://huggingface.co/tencent/Hy-MT2-1.8B/blob/9a341cd1b679d3efd23b46e847b01745a71ed792/LICENSE.txt",
            },
        ),
        (
            "hymt2-7b-q4",
            {
                "title": "Hy-MT2 7B Q4_K_M",
                "filename": "Hy-MT2-7B-Q4_K_M.gguf",
                "repo": "tencent/Hy-MT2-7B-GGUF",
                "revision": "707464294cf5b2a5a69982855020858ed58cf1d1",
                "size": 4624648896,
                "sha256": "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b",
                "license_url": "https://huggingface.co/tencent/Hy-MT2-7B/blob/9b0eb4e8f001def3e5ff6469a0ac96fdb39ec223/LICENSE.txt",
            },
        ),
    )
)

# An individual network operation may block for at most this socket timeout.
# Cancellation is cooperative, checked between reads and before installation.
HTTP_TIMEOUT_SECONDS = 30
_CHUNK_SIZE = 1024 * 1024
_DISK_RESERVE_BYTES = 16 * 1024 * 1024


class ModelDownloadError(Exception):
    """The requested model could not be downloaded or verified."""


class CancelledDownload(ModelDownloadError):
    """The user cancelled a download or local-file verification."""


def _check_cancelled(cancelled):
    if cancelled():
        raise CancelledDownload("Model download or verification cancelled.")


def _get_preset(preset):
    if isinstance(preset, str):
        value = MODEL_PRESETS.get(preset)
    elif isinstance(preset, Mapping):
        value = next((p for p in MODEL_PRESETS.values() if p == preset), None)
    else:
        value = None
    if value is None:
        raise ModelDownloadError("Choose one of the supported offline model presets.")
    value = dict(value)
    # Check catalog mistakes defensively before constructing a URL or file path.
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+\.gguf", value.get("filename", ""))
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value.get("repo", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", value.get("revision", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256", ""))
        or type(value.get("size")) is not int
        or value["size"] <= 0
    ):
        raise ModelDownloadError("The selected model's pinned metadata is invalid.")
    return value


def _require_https(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (
            parsed.scheme.lower() == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        valid = False
    if not valid:
        raise ModelDownloadError("Refusing a model download or redirect outside HTTPS.")


class _HTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _require_https(newurl)
        except ModelDownloadError:
            fp.close()
            raise
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _check_integrity(done, digest, preset):
    if done != preset["size"]:
        raise ModelDownloadError(
            "Model size mismatch: expected {} bytes, received {}. Retry the download."
            .format(preset["size"], done)
        )
    if digest.hexdigest() != preset["sha256"]:
        raise ModelDownloadError(
            "Model SHA-256 mismatch. The file is corrupt or is not the selected "
            "pinned model; download that preset again."
        )


def _file_identity(file_stat):
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def verify_model(path, preset, cancelled=lambda: False, progress=lambda done, total: None):
    """Return ``Path(path)`` only if its bytes match the selected pinned preset.

    ``preset`` is a MODEL_PRESETS key or its unchanged metadata dictionary.
    Nothing is copied, modified, downloaded, or executed. The caller should run
    this potentially large-file operation off the UI thread. Progress reports
    bytes hashed; cancellation raises CancelledDownload.
    """
    preset = _get_preset(preset)
    path = Path(path)
    _check_cancelled(cancelled)
    try:
        if not path.is_file():
            raise ModelDownloadError("Select a regular model file.")
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ModelDownloadError("Select a regular model file.")
            if before.st_size != preset["size"]:
                raise ModelDownloadError(
                    "Model size mismatch: this is not the selected pinned model "
                    "(expected {} bytes, found {}).".format(preset["size"], before.st_size)
                )
            digest = hashlib.sha256()
            done = 0
            progress(0, preset["size"])
            while True:
                _check_cancelled(cancelled)
                chunk = handle.read(_CHUNK_SIZE)
                _check_cancelled(cancelled)
                if not chunk:
                    break
                done += len(chunk)
                if done > preset["size"]:
                    raise ModelDownloadError("Model size changed during verification.")
                digest.update(chunk)
                progress(done, preset["size"])
            _check_integrity(done, digest, preset)
            if (
                _file_identity(before) != _file_identity(os.fstat(handle.fileno()))
                or _file_identity(before) != _file_identity(path.stat())
            ):
                raise ModelDownloadError("Model file changed during verification. Try again.")
        _check_cancelled(cancelled)
        return path
    except OSError as exc:
        raise ModelDownloadError("Cannot read the selected model file: {}".format(exc)) from exc


def download_model(
    preset,
    directory,
    cancelled=lambda: False,
    progress=lambda done, total: None,
    opener=None,
):
    """Download, verify, and atomically install one pinned model, returning its Path.

    Existing verified files are reused without network access. Existing invalid
    files survive cancellation or failure; they are replaced only after the new
    file passes exact size/SHA-256 checks and is flushed to disk. Partials are
    unique to this attempt and removed on failure, so retry starts cleanly.

    For headless tests, ``opener`` may be a callable or an object with ``open``;
    it receives a urllib Request and ``timeout=HTTP_TIMEOUT_SECONDS``. An injected
    opener owns its redirect policy. The production opener rejects non-HTTPS
    redirects before following them, and all final response URLs are checked.
    """
    preset = _get_preset(preset)
    directory = Path(directory)
    destination = directory / preset["filename"]
    partial = None
    _check_cancelled(cancelled)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_file():
                raise ModelDownloadError("The model destination is not a regular file.")
            try:
                return verify_model(destination, preset, cancelled, progress)
            except CancelledDownload:
                raise
            except ModelDownloadError:
                # Preserve this file until a replacement is completely verified.
                pass
        _check_cancelled(cancelled)
        required = preset["size"] + _DISK_RESERVE_BYTES
        free = shutil.disk_usage(directory).free
        if free < required:
            raise ModelDownloadError(
                "Not enough free disk space: need {} bytes (including a 16 MiB "
                "reserve), but only {} bytes are free.".format(required, free)
            )
        url = "https://huggingface.co/{}/resolve/{}/{}".format(
            preset["repo"], preset["revision"], preset["filename"]
        )
        request = urllib.request.Request(
            url,
            headers={"Accept-Encoding": "identity", "User-Agent": "LunaTranslator-offline-models"},
        )
        if opener is None:
            opener = urllib.request.build_opener(_HTTPSRedirectHandler())
        open_url = opener if callable(opener) else opener.open
        _check_cancelled(cancelled)
        with closing(open_url(request, timeout=HTTP_TIMEOUT_SECONDS)) as response:
            _require_https(response.geturl())
            if response.getcode() != 200:
                raise ModelDownloadError(
                    "Model server returned HTTP {}. Retry the download.".format(response.getcode())
                )
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    length = int(length)
                except (ValueError, TypeError):
                    raise ModelDownloadError("Model server returned an invalid Content-Length.")
                if length != preset["size"]:
                    raise ModelDownloadError(
                        "Model server size mismatch: expected {} bytes, announced {}."
                        .format(preset["size"], length)
                    )
            encoding = response.headers.get("Content-Encoding", "identity")
            if encoding.lower().strip() != "identity":
                raise ModelDownloadError("Model server returned an unexpected content encoding.")
            _check_cancelled(cancelled)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix="." + preset["filename"] + ".",
                suffix=".part", dir=directory, delete=False,
            ) as handle:
                partial = Path(handle.name)
                digest = hashlib.sha256()
                done = 0
                progress(0, preset["size"])
                # HTTPResponse.read() can wait to fill the whole buffer through
                # many socket reads. read1() lets cancellation run after each
                # available chunk, including on slow connections.
                read = getattr(response, "read1", response.read)
                while True:
                    _check_cancelled(cancelled)
                    chunk = read(_CHUNK_SIZE)
                    _check_cancelled(cancelled)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > preset["size"]:
                        raise ModelDownloadError("Model download exceeded the pinned file size.")
                    if handle.write(chunk) != len(chunk):
                        raise ModelDownloadError("Could not write the complete model file to disk.")
                    digest.update(chunk)
                    progress(done, preset["size"])
                _check_integrity(done, digest, preset)
                handle.flush()
                os.fsync(handle.fileno())
                if os.fstat(handle.fileno()).st_size != preset["size"]:
                    raise ModelDownloadError("Model file size changed while writing to disk.")
        # Close both file and response before replace (also required on Windows).
        _check_cancelled(cancelled)
        os.replace(partial, destination)
        partial = None
        return destination
    except urllib.error.HTTPError as exc:
        exc.close()
        raise ModelDownloadError("Model download failed: HTTP {}. Retry the download.".format(exc.code)) from exc
    except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise ModelDownloadError("Model download failed: {}. Retry the download.".format(exc)) from exc
    finally:
        if partial is not None:
            try:
                partial.unlink(missing_ok=True)
            except OSError as exc:
                raise ModelDownloadError(
                    "Could not remove the incomplete model file {}: {}".format(partial, exc)
                ) from exc
