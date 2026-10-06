"""Single-attempt coordinator admitted only by the verified Actions entry."""
import base64
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import re
import socket
import shutil
import stat
import sys
import time
import diagnostics
import activation_scope
import actions_policy
import public_exports
import acquisition_source as acquisition
import cpu_harness as h
import guarded_runtime as runtime
import host_validation_source as host
import private_exports_source as exports
from attempt_control import AttemptControl


KIT_CONTRACT_SHA256 = 'ecebb70e442bc3504de892681716abfffe46c16e81dc71f0206029516d14cb32'
def fixed_claim():return runtime.CLAIM_ROOT/'ONE_SHOT_CPU_ATTEMPT.json'


def validate_kit_plan(plan,manifest_sha):
    """Apply unchanged core identities, then explicit superseding operational policy."""
    allowed={'executor','workspace','attempt_id','alias','claimed_utc','pins','assets','limits','sampling',
        'schedule_sha256','commitments','paths','eligibility','output_files','output_policy','redirect_policy',
        'execution_policy','kit_contract_sha256','component_manifest_sha256','host_compatibility',
        'host_compatibility_sha256','port','absolute_python','worker_journal_reserved_bytes','claimed_monotonic',
        'outer_deadline_monotonic','preclaim_host_evidence','preclaim_host_evidence_sha256',
        'roots','provider_binding','source_a','source_parent','coordinator_pid','coordinator_argv'}
    h.require(type(plan) is dict and set(plan)==allowed,'kit plan schema; no criteria/source text fields')
    base=dict(plan);base['redirect_policy']=[]  # Documented legacy-policy validation view only.
    h.validate_claim_plan(base)
    h.require(plan.get('redirect_policy')==acquisition.POLICY,'exact superseding CDN policy')
    h.require(plan.get('kit_contract_sha256')==KIT_CONTRACT_SHA256 and
              plan.get('component_manifest_sha256')==manifest_sha and
              plan['commitments']['harness_manifest']==manifest_sha and
              re.fullmatch('[0-9a-f]{64}',manifest_sha),'kit source/contract bindings')
    actions_policy.validate_provider(plan['provider_binding'],source_a=plan['source_a'],source_parent=plan['source_parent'])
    h.require(type(plan['coordinator_pid']) is int and plan['coordinator_pid']>1,'bound coordinator PID')
    activation_scope.validate_owner_argv(plan['coordinator_argv'],plan['roots'],manifest_sha)
    host.validate_host_plan(plan.get('host_compatibility'))
    h.require(plan.get('host_compatibility_sha256')==h.digest(h.canonical(plan['host_compatibility'])),
              'host policy digest')
    h.require(type(plan.get('port')) is int and 1024<=plan['port']<=65535 and
              Path(plan.get('absolute_python','')).is_absolute(),'port/Python binding')
    h.require(plan.get('worker_journal_reserved_bytes')==65536,'worker shared-output reservation')
    for key in ('claimed_monotonic','outer_deadline_monotonic'):
        h.require(type(plan.get(key)) in (int,float) and math.isfinite(plan[key]),'attempt monotonic stamps')
    h.require(plan['outer_deadline_monotonic']==plan['claimed_monotonic']+1475,'fixed outer attempt deadline')
    h.require(plan.get('preclaim_host_evidence_sha256')==h.digest(h.canonical(plan.get('preclaim_host_evidence'))),
              'preclaim host evidence binding')
    out=Path(plan['paths']['output'])
    h.require(out==Path(plan['roots']['output']) and '..' not in out.parts and
              plan['paths']['acquisition']==str(out/'staging') and
              plan['paths']['extraction']==str(out/'runtime'),'single owned private attempt root')
    return True


def claim_once(plan,manifest_sha,trace=None):
    runtime.require_activation();validate_kit_plan(plan,manifest_sha)
    raw=h.canonical(plan);h.require(len(raw)<=32768,'claim size')
    root_fd=claim_fd=journal=None;failure=None
    def latch(exc):
        nonlocal failure
        if failure is None:
            failure=exc
            if trace:trace.fail(exc)
    def close_owned(fd,stage,category):
        if fd is None:return
        if trace:trace.enter(stage)
        try:os.close(fd)
        except BaseException as exc:
            latch(exc)
            if trace:trace.cleanup_issue(category)
    try:
        runtime.persistence_checkpoint()
        if trace:trace.enter('CLAIM_CREATE')
        root_fd=os.open(runtime.CLAIM_ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        runtime.persistence_checkpoint()
        if trace:trace.claim='CREATE_PENDING'
        claim_fd=os.open(fixed_claim().name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=root_fd)
        if trace:trace.claim='CREATED';trace.enter('CLAIM_WRITE')
        try:runtime.persistent_write(claim_fd,raw)
        except BaseException as exc:latch(exc)
        finally:
            closing,claim_fd=claim_fd,None  # Relinquish before one close attempt; never retry an ambiguous close.
            close_owned(closing,'CLAIM_FILE_CLOSE','CLAIM_FILE_CLOSE_FAILED')
        if failure is not None:raise failure
        if trace:trace.enter('CLAIM_SYNC')
        runtime.persistence_checkpoint();os.fsync(root_fd);runtime.persistence_checkpoint()
        if trace:trace.claim='DURABLE';trace.enter('JOURNAL_CREATE');trace.journal='CREATE_PENDING'
        journal=os.open('ONE_SHOT_CPU_EVENTS.jsonl',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_APPEND|os.O_NOFOLLOW,
                        0o600,dir_fd=root_fd)
        if trace:trace.journal='OPEN';trace.enter('JOURNAL_SYNC')
        runtime.persistence_checkpoint();os.fsync(root_fd);runtime.persistence_checkpoint()
        if trace:trace.journal='DURABLE'
    except BaseException as exc:latch(exc)
    finally:
        closing,claim_fd=claim_fd,None
        close_owned(closing,'CLAIM_FILE_CLOSE','CLAIM_FILE_CLOSE_FAILED')
        closing,root_fd=root_fd,None
        close_owned(closing,'CLAIM_DIRECTORY_CLOSE','CLAIM_DIRECTORY_CLOSE_FAILED')
        if failure is not None:
            closing,journal=journal,None
            close_owned(closing,'JOURNAL_CLOSE','JOURNAL_CLOSE_FAILED')
    if failure is not None:raise failure
    # Ownership transfers only after every local finalization operation succeeded.
    return journal


def verified_python_spec(plan,mode,argument):
    h.require(mode in ('acquire','validate','helper'),'one declared worker phase')
    return h.child_spec(plan['absolute_python'],['-I','-B',str(runtime.HERE/'verified_bootstrap.py'),
        str(runtime.HERE/'KIT_MANIFEST.json'),plan['component_manifest_sha256'],mode,str(argument)],
        plan['paths']['output'])


def wait_owned(supervisor,name):
    runtime.require_activation()
    intent=supervisor.intents[name];proc=intent.process
    while proc.poll() is None:
        supervisor.check();supervisor.stop_event.wait(.05)
    if supervisor.diagnostic:supervisor.diagnostic.child(name,exit='EXITED',exit_code=proc.returncode)
    h.require(proc.returncode==0,'owned '+name+' failed')
    intent.exit_confirmed=True
    # Each worker has one stdout reader, most recently registered by launch.
    reader=supervisor.readers[-1]
    reader.join(timeout=max(0,supervisor.phase_end-time.monotonic()))
    h.require(not reader.is_alive(),'owned '+name+' log reader unfinished')
    supervisor.check()


def run_worker(supervisor,plan,mode):
    runtime.require_activation()
    seconds=600 if mode=='acquire' else 60
    supervisor.set_phase(mode,seconds)
    supervisor.launch(mode,verified_python_spec(plan,mode,fixed_claim()),seconds,'validation.log')
    wait_owned(supervisor,mode)
    raw=runtime.bounded_file(Path(plan['paths']['output'])/'validation.log',65536)
    lines=raw.splitlines();h.require(lines and len(lines[-1])<=65536,'worker result line')
    result=h.strict_json(lines[-1])
    h.require(result.get('status')=='complete' and result.get('phase')==mode and
              type(result.get('journal_bytes')) is int and 0<=result['journal_bytes']<=32768,'worker receipt')
    supervisor.record(dict(event='worker_receipt',phase=mode,result=result))
    return result['result']


class KitLedger(h.RequestLedger):
    def __init__(self,persist,publish_preflight):
        super().__init__(persist);self.publish_preflight=publish_preflight
    def seal_preflight(self,plans):
        try:
            h.require(self.terminal is None and self.total==178 and not self.preflight_sealed,'preflight publication boundary')
            self.publish_preflight(plans)
            super().seal_preflight(plans)
            self.plans=tuple(plans)
        except BaseException:
            self.fail('preflight_publication_or_validation_failure')
            raise


class KitSupervisor(runtime.OwnedSupervisor):
    def __init__(self,*args,plan,**kwargs):
        super().__init__(*args,**kwargs);self.plan=plan
    def publish_preflight(self,plans):
        runtime.require_activation();self.check()
        receipt=public_exports.preflight_receipt(plans,self.plan['component_manifest_sha256'],
                                                 self.plan['commitments']['source_plan'])
        self.evidence.json('metadata.json',dict(event='public_preflight',receipt=receipt))
        self.check()
        sys.stdout.buffer.write(b'LUNA_PREFLIGHT_JSON '+h.canonical(receipt)+b'\n');sys.stdout.buffer.flush()
        self.check()
    def launch(self,name,spec,seconds,log_name):
        runtime.require_activation()
        if name=='helper':
            h.require(spec['executable']==self.plan['absolute_python'] and
                      str(runtime.HERE/'isolated_helper.py') in spec['argv'],'only declared helper adaptation')
            spec=verified_python_spec(self.plan,'helper',Path(self.plan['paths']['output'])/'helper_input.json')
        return super().launch(name,spec,seconds,log_name)


def recheck_launch_resources(plan,resources):
    runtime.require_activation()
    available=resources.memory_available()
    h.require(host.namespace_observation(runtime.bounded_file,os.readlink)==plan['preclaim_host_evidence']['namespaces'],
              'namespace drift before launch')
    host.recheck_host_bindings(plan['preclaim_host_evidence']['resolved_host'],h.Deadline(time.monotonic,15))
    effective=runtime.cgroup_headroom(available,hierarchy_root_verified=True)
    free=shutil.disk_usage(plan['paths']['output']).free
    # Acquisition requires 3 GiB initially; execution keeps the original 1 GiB floor.
    h.require(free>=h.GIB,'execution free disk floor')
    h.require(type(available) is int and type(effective) is int and
              min(available,effective)>=h.LIMITS['startup_ram'],'fresh startup host/cgroup reserve')
    return dict(available_ram=available,effective_headroom=effective,free_disk=free)


def check_private_preparation(plan):
    runtime.require_activation()
    out=Path(plan['paths']['output'])
    h.require(out.is_dir() and not out.is_symlink() and out.stat().st_uid==os.geteuid() and
              out.stat().st_mode&0o777==0o700,'private prepared output root')
    h.require(set(os.listdir(out))==set(),'fresh empty output; no arm-key channel')
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1',plan['port']))


def collect_worker_diagnostics(owner,evidence,trace):
    for name in ('validation.log','helper.log'):
        if name not in evidence.file_bytes:continue
        try:
            raw=runtime.bounded_file(evidence.output/name,65536)
            for line in raw.splitlines():
                if line.startswith(b'LUNA_WORKER_DIAGNOSTIC '):
                    value=h.strict_json(line[len(b'LUNA_WORKER_DIAGNOSTIC '):]);trace.merge_worker(value)
                elif line.startswith(b'{'):
                    value=h.strict_json(line)
                    if type(value) is dict and 'diagnostic' in value:trace.merge_worker(value['diagnostic'])
        except BaseException:
            # Missing/truncated diagnostics do not fabricate a zero counter.
            continue


def emit_public_snapshot(plan,owner,evidence,protocol_complete):
    """Only reviewed schema leaves the VM. All raw evidence stays temporary."""
    runtime.require_activation();runtime.persistence_checkpoint()
    sources=runtime.load_source_only_rows();observations={};wires=[]
    out=Path(plan['paths']['output'])
    for name in ('results.jsonl','wire.jsonl'):
        if name not in evidence.file_bytes:continue
        raw=runtime.bounded_file(out/name,64*h.MIB)
        lines=raw.splitlines();h.require(len(lines)<=(176 if name=='results.jsonl' else 442),'public record bound')
        for line in lines:
            item=h.strict_json(line)
            if name=='results.jsonl':
                identity=(item['row'],item['arm']);h.require(identity not in observations,'duplicate public arm')
                observations[identity]=dict(status=item.get('status','observed'),**{k:v for k,v in item.items() if k!='status'})
            else:wires.append(item)
    ledger=getattr(owner,'public_ledger',None)
    consumed=0 if ledger is None else ledger.total
    numbers=[w['request_number'] for w in wires if w.get('attempted')]
    confirmed=numbers==list(range(1,consumed+1))
    validated=sum(w.get('status')=='validated' for w in wires)
    if confirmed:
        h.require(all(w.get('status')=='validated' for w in wires[:validated]),'validated response prefix')
    payloads=public_exports.build_public(sources,observations,consumed_http=consumed if confirmed else None,
        validated_http=validated if confirmed else None,accounting_confirmed=confirmed,
        status='complete' if protocol_complete else 'incomplete',resource_metrics={
        'runner_peak_rss_bytes':owner.peak_runner_rss,'server_peak_rss_bytes':owner.peak_server_rss,
        **getattr(owner,'public_helper_metrics',{})},
        protocol=getattr(owner,'public_reconciliation',None),diagnostic=owner.diagnostic.snapshot() if owner.diagnostic else None)
    runtime.persistence_checkpoint();os.mkdir(out/'public',0o700)
    for name,value in payloads.items():
        runtime.persistence_checkpoint();evidence.create('public/'+name);evidence.json('public/'+name,value)
        # Fixed prefix and canonical JSON escape model newlines/control characters.
        # No generic log/file upload: root retrieves these allowlisted records.
        line=b'LUNA_PUBLIC_JSON '+h.canonical(dict(snapshot='final',file=name,data=value))+b'\n'
        sys.stdout.buffer.write(line);sys.stdout.buffer.flush();runtime.persistence_checkpoint()


def run_stages(plan,owner,evidence,resources,error_type,integrity):
    """Single declared path; any raised failure returns directly to finalization."""
    runtime.require_activation()
    if owner.diagnostic:owner.diagnostic.enter('EVIDENCE_INIT')
    for name in ('metadata.json','wire.jsonl','results.jsonl','all_rows.json','validation.log','version.log','server.log'):
        evidence.create(name)
    owner.record(dict(event='claimed',attempt_id=plan['attempt_id'],alias=plan['alias']))
    evidence.json('metadata.json',dict(event='bound_plan',kit_contract_sha256=KIT_CONTRACT_SHA256,
        component_manifest_sha256=plan['component_manifest_sha256'],host=plan['preclaim_host_evidence'],
        timing_clock=vars(time.get_clock_info('perf_counter'))))
    os.mkdir(plan['paths']['acquisition'],0o700)
    assets=run_worker(owner,plan,'acquire')
    evidence.json('metadata.json',dict(event='acquired',receipt=assets))
    validated=run_worker(owner,plan,'validate')
    manifest_raw=runtime.bounded_file(Path(plan['paths']['output'])/'archive_members.json',h.MIB)
    h.require(h.digest(manifest_raw)==validated['member_manifest_sha256'],'worker member receipt drift')
    runtime_identity=validated['runtime'];server=runtime_identity['server']
    dirs=runtime_identity['library_dirs']
    expected_dirs=[str((Path(plan['paths']['extraction'])/p).resolve()) for p in plan['host_compatibility']['archive_library_dirs']]
    h.require(dirs==expected_dirs,'reviewed ordered library directories')
    version_spec=h.child_spec(server,['--version'],plan['paths']['output'])
    if dirs:version_spec['env']['LD_LIBRARY_PATH']=':'.join(dirs)
    owner.set_phase('version',15);owner.launch('version',version_spec,15,'version.log');wait_owned(owner,'version')
    version=runtime.bounded_file(Path(plan['paths']['output'])/'version.log',65536).decode('utf-8','strict')
    h.require('build 11349, commit fb4b2737a' in version,'pinned runtime version/commit')
    template=runtime.AUDITED/'hymt_chat_template.jinja'
    runtime.pinned_file(template,h.PINS['template'],65536)
    resources_at_launch=recheck_launch_resources(plan,resources)
    evidence.json('metadata.json',dict(event='immediate_prelaunch_resources',**resources_at_launch))
    spec=h.server_spec(server,str(Path(plan['paths']['acquisition'])/'model.gguf'),str(template),
                       plan['paths']['output'],plan['port'],plan['alias'])
    if dirs:spec['env']['LD_LIBRARY_PATH']=':'.join(dirs)
    owner.set_phase('startup',180);owner.launch('server',spec,180,'server.log')
    sources=runtime.load_source_only_rows()
    lexicon=runtime.pinned_file(runtime.ROOT/'inputs/runtimelexicon.json',h.PINS['lexicon'],8192)
    transport=runtime.LoopbackTransport(owner,plan['port']);ledger=KitLedger(owner.record,owner.publish_preflight);owner.public_ledger=ledger
    observations,totals=runtime.execute_generation_stage(owner,transport,plan['alias'],lexicon,sources,
        integrity,error_type,evidence,ledger)
    if owner.diagnostic:owner.diagnostic.enter('RECONCILE')
    reconciliation=runtime.reconcile_completed_evidence(evidence,ledger.plans,sources,plan['alias'],lexicon,integrity,error_type)
    owner.public_reconciliation=reconciliation
    evidence.json('metadata.json',dict(event='generation_completed',totals=totals,
        runner_peak_rss=owner.peak_runner_rss,server_peak_rss=owner.peak_server_rss,
        protocol_status=reconciliation['status'],cost_status=reconciliation['cost']['status']))
    owner.check()
    return dict(protocol_complete=True,semantic_quality_claim=None)


def _run_attempt(encoded_plan,manifest_sha,control):
    """One prospective path only. Gate raises before decode, host read or claim."""
    runtime.require_activation()
    control.checkpoint()
    h.require(globals().get('_VERIFIED_BOOTSTRAP_SHA')==manifest_sha,'verified source bootstrap required')
    h.require(type(encoded_plan) is str and len(encoded_plan)<=45000,'bounded plan argument')
    raw=base64.b64decode(encoded_plan,validate=True);h.require(len(raw)<=32768,'plan cap')
    plan=h.strict_json(raw)
    trace=getattr(control,'diagnostic',None)
    if trace:trace.bind_attempt(plan.get('attempt_id'));trace.enter('PLAN_CHECK')
    runtime.bind_actions_roots(plan['roots']);validate_kit_plan(plan,manifest_sha)
    h.require(str(Path(sys.executable).resolve())==plan['absolute_python'] and
              os.getpid()==plan['coordinator_pid'],'existing isolated Python/coordinator identity')
    h.require(not os.path.lexists(fixed_claim()),'one-shot claim already exists or is ambiguous')
    resources,error_type,integrity=runtime.load_audited_components()
    # These non-mutating checks happen BEFORE any new claim or 1.15 GB download.
    if trace:trace.enter('PRECLAIM_HOST')
    host_evidence=host.check_host_before_claim(plan['host_compatibility'],resources,plan['roots']['runner_temp'],
        plan['provider_binding'],plan['source_a'],plan['source_parent'])
    control.checkpoint()
    if trace:trace.enter('OUTPUT_PREPARATION')
    check_private_preparation(plan)
    plan['preclaim_host_evidence']=host_evidence
    plan['preclaim_host_evidence_sha256']=h.digest(h.canonical(host_evidence))
    plan['claimed_utc']=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    plan['claimed_monotonic']=time.monotonic();plan['outer_deadline_monotonic']=plan['claimed_monotonic']+1475
    validate_kit_plan(plan,manifest_sha)
    evidence=runtime.EvidenceFiles(plan['paths']['output'],initial_claim_size=len(h.canonical(plan)))
    # Reserve before workers can retain their externally written journal/member bytes.
    evidence.budget.retain(b'\0'*(65536+h.MIB))
    owner=KitSupervisor(plan['claimed_monotonic'],None,evidence,resources,plan['paths']['output'],
        full_cgroup_ancestry_verified=True,plan=plan)
    owner.diagnostic=trace
    control.bind_owner(owner);control.checkpoint()
    journal=None;protocol_complete=False;failure=None
    try:
        if trace:trace.enter('OWNER_ARM')
        owner.arm()  # Outer monitor is already armed before claim serialization/fsync.
        journal=claim_once(plan,manifest_sha,trace);owner.journal=journal;owner.check()
        result=run_stages(plan,owner,evidence,resources,error_type,integrity)
        protocol_complete=result['protocol_complete']
    except BaseException as exc:
        if trace:trace.fail(exc)
        failure=type(exc).__name__;owner.fail('attempt failed: '+failure)
    finally:
        if trace:trace.enter('CLEANUP')
        control.begin_cleanup()
        end=control.cleanup_deadline()
        try:
            control.checkpoint()
            if 'all_rows.json' in evidence.files and evidence.file_bytes['all_rows.json']==0:
                evidence.json('all_rows.json',h.all_row_accounting({}))
        except BaseException as exc:owner.cleanup_errors.append('all-row finalization: '+type(exc).__name__)
        status=owner.finalize()
        if trace:collect_worker_diagnostics(owner,evidence,trace)
        try:
            if trace:trace.enter('PUBLIC_EXPORT')
            emit_public_snapshot(plan,owner,evidence,protocol_complete)
        except BaseException as exc:
            status.update(status='incomplete',cleanup_confirmed=False)
            status.setdefault('unresolved',[]).append('public export incomplete: '+type(exc).__name__)
            if trace:trace.fail(exc,code='PUBLIC_EXPORT_FAILED');trace.cleanup_issue('PUBLIC_EXPORT_FAILED')
        if journal is not None:
            try:os.close(journal)
            except BaseException:
                status.update(status='incomplete',cleanup_confirmed=False)
                if trace:trace.cleanup_issue('JOURNAL_CLOSE_FAILED')
        try:
            control.checkpoint()
            deadline=h.Deadline(time.monotonic,20,end)
            if trace:trace.enter('MANIFEST')
            manifest=exports.manifest_private_files(plan,deadline,status)
            control.checkpoint()
            evidence.create('manifest.json');evidence.json('manifest.json',manifest);evidence.close()
            directory=os.open(plan['paths']['output'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:control.checkpoint();os.fsync(directory);control.checkpoint()
            finally:os.close(directory)
            deadline.remaining()
        except BaseException as exc:
            status.update(status='incomplete',cleanup_confirmed=False)
            status.setdefault('unresolved',[]).append('manifest/finalization: '+type(exc).__name__)
            if trace:trace.fail(exc,code='MANIFEST_FAILED');trace.cleanup_issue('MANIFEST_FAILED')
    status.update(protocol_complete=protocol_complete,semantic_quality_claim=None,
                  attempt_id=plan['attempt_id'],failure=failure)
    if not protocol_complete:status['status']='incomplete'
    return status


def main(encoded_plan,manifest_sha):
    runtime.require_activation()
    activation_scope.require_role('actions')
    trace=diagnostics.Trace(manifest_sha);trace.enter('PLAN_CHECK')
    return AttemptControl(diagnostic=trace).run(lambda control:_run_attempt(encoded_plan,manifest_sha,control))
