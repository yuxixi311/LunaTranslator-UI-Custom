"""Acquisition/validation workers require exact owned-parent claim admission."""
import os
from pathlib import Path
import time
import sys
import diagnostics
import activation_scope
import acquisition_source as acquisition
import cpu_harness as h
import guarded_runtime as runtime
import host_validation_source as host


class WorkerJournal:
    def __init__(self):self.fd=None;self.bytes=0
    def open(self):
        runtime.require_activation()
        self.fd=os.open(runtime.CLAIM_ROOT/'ONE_SHOT_CPU_EVENTS.jsonl',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
    def event(self,event):
        runtime.require_activation()
        raw=h.canonical(event)+b'\n'
        h.require(len(raw)<=4096 and self.bytes+len(raw)<=32768,'worker journal reservation')
        self.bytes+=len(raw)
        n=os.write(self.fd,raw);h.require(n==len(raw),'partial worker journal write')
        os.fsync(self.fd)
    def close(self):
        runtime.require_activation()
        if self.fd is not None:os.close(self.fd)


def main(mode,claim_path,manifest_sha):
    runtime.require_activation()
    from final_coordinator import validate_kit_plan
    raw=runtime.bounded_file(claim_path,32768)
    grant=activation_scope.require_role(mode)
    h.require(h.digest(raw)==grant['claim_sha256'],'worker claim drift after activation')
    plan=h.strict_json(raw)
    runtime.bind_actions_roots(plan['roots'])
    h.require(Path(claim_path)==runtime.CLAIM_ROOT/'ONE_SHOT_CPU_ATTEMPT.json','worker fixed claim')
    validate_kit_plan(plan,manifest_sha)
    deadline=h.Deadline(time.monotonic,600 if mode=='acquire' else 60,plan['outer_deadline_monotonic'])
    trace=diagnostics.Trace(manifest_sha,plan['attempt_id'],mode);trace.enter('WORKER_JOURNAL')
    journal=WorkerJournal();result=None;failed=False
    try:
        journal.open()
        journal.event(dict(event='worker_phase',phase=mode))
        if mode=='acquire':
            result=acquisition.acquire_assets(plan['paths']['acquisition'],deadline,journal.event,trace)
        elif mode=='validate':
            staging=Path(plan['paths']['acquisition'])
            for index,name in enumerate(('model.gguf','runtime.tar.gz')):
                h.require(host.hash_file(staging/name,deadline,h.ASSETS[index][1])==h.ASSETS[index][2],
                          'revalidate acquired asset identity')
            trace.enter('EXTRACTION')
            members=acquisition.extract_archive(staging/'runtime.tar.gz',plan['paths']['extraction'],deadline)
            trace.enter('RUNTIME_VALIDATE')
            runtime_result=host.validate_extracted_runtime(plan['preclaim_host_evidence']['resolved_host'],plan['paths']['extraction'],members,deadline)
            member_bytes=h.canonical(dict(archive_sha256=h.PINS['runtime_archive'],members=members,runtime=runtime_result))
            h.require(len(member_bytes)<=h.MIB,'member manifest cap')
            output=Path(plan['paths']['output'])/'archive_members.json'
            fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:runtime.persistent_write(fd,member_bytes)
            finally:os.close(fd)
            result=dict(member_manifest_sha256=h.digest(member_bytes),member_manifest_bytes=len(member_bytes),
                        runtime=runtime_result,notices_preserved=[m['name'] for m in members if
                        any(term in Path(m['name']).name.lower() for term in ('license','notice','copying'))])
        else:raise h.TerminalFailure('worker mode')
        deadline.remaining();journal.event(dict(event='worker_complete',phase=mode))
    except BaseException as exc:
        trace.fail(exc);failed=True
        if journal.fd is not None:
            try:journal.event(dict(event='worker_failed',phase=mode,code=diagnostics.category(exc)))
            except BaseException as journal_error:trace.fail(journal_error,stage='WORKER_JOURNAL')
    finally:
        try:journal.close()
        except BaseException as exc:
            trace.fail(exc,stage='WORKER_JOURNAL');trace.cleanup_issue('JOURNAL_CLOSE_FAILED');failed=True
    if failed:
        sys.stdout.buffer.write(diagnostics.worker_line(trace));sys.stdout.buffer.flush()
        raise SystemExit(1) from None
    encoded=h.canonical(dict(status='complete',phase=mode,result=result,journal_bytes=journal.bytes,
                             diagnostic=trace.worker_snapshot()))
    h.require(len(encoded)<=65536,'worker diagnostic cap')
    sys.stdout.buffer.write(encoded+b'\n');sys.stdout.buffer.flush()
