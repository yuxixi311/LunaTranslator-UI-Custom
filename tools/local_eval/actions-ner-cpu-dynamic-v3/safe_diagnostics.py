"""Finite, binding-checked child diagnostics; no raw exception text is emitted."""
import os
import socket
import subprocess
import sys
import urllib.error
from ner_adapter import ProbeFailure, require
from runner_control import exclusive_json, file_pin
from wheel_validation_codes import WHEEL_SUBCHECKS, ACCEPTED_METADATA_VERSIONS, METADATA_VERSION_OBSERVATIONS

PROBE_CODES = frozenset({'invalid_diagnostic_state', 'diagnostic_binding_changed', 'unexpected_child_error_receipt', 'failure_binding_mismatch'}) | frozenset(['artifact_changed', 'attempt_already_exists', 'bootstrap_archive_hash_mismatch', 'bootstrap_directory_payload', 'bootstrap_duplicate_path', 'bootstrap_import_origin', 'bootstrap_member_count', 'bootstrap_metadata_hash', 'bootstrap_metadata_mismatch', 'bootstrap_missing_metadata', 'bootstrap_path_mismatch', 'bootstrap_record_hash', 'bootstrap_record_inventory', 'bootstrap_record_self_hash', 'bootstrap_startup_or_native_code', 'bootstrap_uncompressed_budget', 'bootstrap_unsafe_member', 'bootstrap_unsafe_path', 'bootstrap_wheel_tag', 'child_binding_mismatch', 'child_context_changed', 'child_parent_mismatch', 'cold_gate_failed', 'cpu_gate_failed', 'decision_replay_mismatch', 'dependency_manifest_mismatch', 'document_text_mismatch', 'download_budget_exceeded', 'download_count_mismatch', 'download_deadline', 'download_inventory_changed', 'download_receipt_mismatch', 'duplicate_canon_destination', 'duplicate_case_id', 'duplicate_json_key', 'entity_token_alignment_mismatch', 'event_binding_changed', 'evidence_binding_mismatch', 'evidence_population_mismatch', 'file_hash_mismatch', 'file_type_or_size_mismatch', 'fixture_freeze_mismatch', 'fixture_roles_mismatch', 'fresh_format_mismatch', 'host_identity_changed', 'incomplete_evidence_population', 'installed_inventory_changed', 'installed_path_escape', 'installed_payload_changed', 'installed_record_incomplete', 'installed_size_exceeded', 'installed_size_mismatch', 'installed_special_file', 'installed_symlink', 'installer_parent_mismatch', 'installer_venv_mismatch', 'insufficient_disk', 'insufficient_ram', 'interpreter_hash_mismatch', 'invalid_bindings', 'invalid_canon', 'invalid_canon_destination', 'invalid_canon_document', 'invalid_case_document', 'invalid_case_id', 'invalid_child_arguments', 'invalid_child_paths', 'invalid_entities', 'invalid_entity_evidence', 'invalid_evidence_row', 'invalid_evidence_schema', 'invalid_file_pin', 'invalid_input_bindings', 'invalid_install_wheels', 'invalid_installed_record', 'invalid_installer_command', 'invalid_json', 'invalid_json_number', 'invalid_lifecycle', 'invalid_metrics', 'invalid_population', 'invalid_receipt', 'invalid_resource_measurement', 'invalid_run_arguments', 'invalid_smoke_evidence', 'invalid_source', 'invalid_source_inventory_hash', 'invalid_stage', 'invalid_timing', 'invalid_token_evidence', 'invalid_token_gap', 'invalid_tokens', 'invalid_wheel_response', 'json_size_exceeded', 'metadata_receipt_mismatch', 'metrics_replay_mismatch', 'missing_person_label', 'missing_runtime_tags', 'model_inventory_mismatch', 'nonofficial_wheel_url', 'notice_inventory_changed', 'offline_install_failed', 'offline_network_denied', 'output_size_exceeded', 'parser_parent_mismatch', 'parser_venv_mismatch', 'phase_order_mismatch', 'policy_hash_mismatch', 'population_binding_mismatch', 'population_count_mismatch', 'preexisting_packaging_forbidden', 'receipt_binding_mismatch', 'receipt_changed', 'redirect_forbidden', 'resource_gate_mismatch', 'rss_gate_failed', 'runtime_cache_mismatch', 'setup_receipt_mismatch', 'source_hash_mismatch', 'source_inventory_mismatch', 'stage_start_mismatch', 'supplement_copy_mismatch', 'supplement_hash_mismatch', 'terminal_attempt', 'unexpected_pipeline', 'unexpected_tokenizer', 'unsafe_artifact', 'unsafe_file_path', 'unsafe_install_root', 'unsafe_work_directory', 'unsupported_host', 'unsupported_libc', 'venv_interpreter_mismatch', 'venv_not_isolated', 'version_mismatch', 'warm_p95_gate_failed', 'wheel_hash_mismatch', 'wheel_size_mismatch', 'wheelhouse_inventory_mismatch'])
PACKAGES = frozenset(['annotated-doc', 'annotated-types', 'anyio', 'blis', 'catalogue', 'certifi', 'charset-normalizer', 'click', 'cloudpathlib', 'confection', 'cymem', 'ginza', 'h11', 'httpcore', 'httpx', 'idna', 'ja-ginza', 'jinja2', 'markdown-it-py', 'markupsafe', 'mdurl', 'murmurhash', 'numpy', 'packaging', 'plac', 'preshed', 'pydantic', 'pydantic-core', 'pygments', 'requests', 'rich', 'setuptools', 'shellingham', 'smart-open', 'spacy', 'spacy-legacy', 'spacy-loggers', 'srsly', 'sudachidict-core', 'sudachipy', 'thinc', 'tqdm', 'typer', 'typing-extensions', 'typing-inspection', 'urllib3', 'wasabi', 'weasel', 'wrapt'])
STEPS = frozenset({'source_binding','host_binding','prerequisite_receipts','download','wheel_inventory',
    'packaging_bootstrap','wheel_validation','notice_retention','venv_create','venv_identity','ensurepip',
    'install','payload_retention','model_inventory','installed_snapshot','setup_output','installed_verification','ner_pipeline'})
GENERIC_CODES = frozenset({'http_failure','dns_failure','network_failure','timeout','permission_rejected',
    'installer_process_failed','wheel_validation_failed','unknown_failure'})


def error_code(exc):
    if type(exc) is ProbeFailure and exc.category in PROBE_CODES:
        return exc.category
    if isinstance(exc, urllib.error.HTTPError): return 'http_failure'
    if isinstance(exc, urllib.error.URLError):
        return 'dns_failure' if isinstance(exc.reason, socket.gaierror) else 'network_failure'
    if isinstance(exc, socket.gaierror): return 'dns_failure'
    if isinstance(exc, TimeoutError): return 'timeout'
    if isinstance(exc, PermissionError): return 'permission_rejected'
    if isinstance(exc, subprocess.CalledProcessError): return 'installer_process_failed'
    module = sys.modules.get('wheel_validation')
    if module is not None and type(exc) is module.WheelValidationError: return 'wheel_validation_failed'
    return 'unknown_failure'


def wheel_subcheck(exc):
    """Never derive a public label from an exception message or foreign object."""
    module = sys.modules.get('wheel_validation')
    if module is None or type(exc) is not module.WheelValidationError:
        return None
    value = getattr(exc, 'subcheck', None)
    return value if type(value) is str and value in WHEEL_SUBCHECKS else 'unclassified'


def wheel_metadata_version(exc):
    if wheel_subcheck(exc) != 'metadata_version_unsupported':
        return None
    value = getattr(exc, 'observed_metadata_version', None)
    return value if type(value) is str and value in METADATA_VERSION_OBSERVATIONS else 'other'


class Diagnostics:
    def __init__(self, work, stage, source_sha, claim_sha, context_sha):
        self.work, self.stage = work, stage
        self.identity = {'stage': stage, 'source_inventory_sha256': source_sha,
                         'claim_sha256': claim_sha, 'context_sha256': context_sha}
        self.step, self.package, self.sequence = 'source_binding', None, 0

    def mark(self, step, package=None):
        require(step in STEPS and (package is None or package in PACKAGES), 'invalid_diagnostic_state')
        require(self.sequence < 128, 'invalid_diagnostic_state')
        self.step, self.package = step, package
        self.sequence += 1
        next_path = self.work / (self.stage + '.progress.next')
        exclusive_json(next_path, {**self.identity, 'step': step, 'package': package, 'sequence': self.sequence})
        os.replace(next_path, self.work / (self.stage + '.progress.json'))

    def fail(self, exc):
        # Recheck both immutable binding files immediately before sealing.
        require(file_pin(self.work / 'RUN_CLAIM.json')['sha256'] == self.identity['claim_sha256']
                and file_pin(self.work / (self.stage + '.context.json'))['sha256'] == self.identity['context_sha256'],
                'diagnostic_binding_changed')
        exclusive_json(self.work / (self.stage + '.error.json'),
            {**self.identity, 'code': error_code(exc), 'wheel_subcheck': wheel_subcheck(exc),
             'wheel_metadata_version': wheel_metadata_version(exc),
             'step': self.step, 'package': self.package})
