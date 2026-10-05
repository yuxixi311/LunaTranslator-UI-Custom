#!/bin/sh
# SOURCE-ONLY TEMPLATE. Do not release or run against the network without review.
# No installer, checkout, cache, artifact upload, or interpreter download.
set -eu

SOURCE_ONLY=0
EXPECTED_SOURCE_SHA256=5a1faf62d278276c0d2ca9045c6d59e673d3f81c84ba1eda304b785368a6c887
TIMEOUT_BIN=/usr/bin/timeout

emit_code() {
    # All callers use fixed, reviewed literals; never interpolate an exception.
    printf '{"status":"blocked","code":"%s"}\n' "$1"
}

if [ "$SOURCE_ONLY" -ne 0 ]; then
    emit_code source_only_disabled
    exit 2
fi

if [ ! -x "$TIMEOUT_BIN" ]; then
    emit_code missing_existing_timeout
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    emit_code missing_existing_python
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)
source_file="$script_dir/ner_metadata_fetcher_review.py"
if [ ! -f "$source_file" ]; then
    emit_code missing_reviewed_source
    exit 2
fi
if ! actual_digest=$(sha256sum -- "$source_file" 2>/dev/null); then
    emit_code source_hash_unavailable
    exit 2
fi
actual_digest=${actual_digest%% *}
if [ "$actual_digest" != "$EXPECTED_SOURCE_SHA256" ]; then
    emit_code source_hash_mismatch
    exit 2
fi

# A subprocess supervisor also bounds native DNS/TLS stalls. Its TERM at 55 s
# and KILL five seconds later bound the owned reader lifecycle to 60 s under
# normal OS scheduling and signal-delivery assumptions. The
# collector has a separate 50 s active budget for a clean partial receipt.
# Metadata JSON is captured in memory; child stderr is never published.
set +e
public_output=$("$TIMEOUT_BIN" --signal=TERM --kill-after=5s 55s python3 -I -B "$source_file" </dev/null 2>/dev/null)
status=$?
set -e

case "$status" in
    0|2)
        # The hash-verified reader emits ASCII JSON with a 64 KiB byte cap.
        # Shell capture removes its final newline, hence the strict < 65536.
        if [ "${#public_output}" -ge 65536 ]; then
            emit_code output_limit
            exit 2
        fi
        case "$public_output" in
            \{*\}) printf '%s\n' "$public_output" ;;
            *) emit_code missing_public_receipt; exit 2 ;;
        esac
        exit "$status"
        ;;
    124|137|143)
        emit_code process_deadline
        exit 2
        ;;
    130)
        emit_code cancelled
        exit 2
        ;;
    *)
        emit_code process_failure
        exit 2
        ;;
esac
