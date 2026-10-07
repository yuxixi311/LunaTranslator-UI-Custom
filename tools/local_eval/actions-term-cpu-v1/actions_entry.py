"""Verified Actions A→B admission wrapper; no REST or extra execution phase."""
import base64
from copy import deepcopy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import activation_scope
import actions_policy as policy
import cpu_harness as h
import guarded_runtime as runtime
import host_validation_source as host
import acquisition_source as acquisition
import final_coordinator as coordinator
import term_public_exports as public_exports
import term_runtime_inventory


def provider_binding(event,env,git,*,source_parent):
    """Pure with an inert git callback. Only explicit provider fields are copied."""
    h.require(env.get('GITHUB_ACTIONS')=='true','GitHub service context required')
    source=env['LUNA_SOURCE_COMMIT'];after=env['GITHUB_SHA']
    h.require(event['repository']['full_name']==env['GITHUB_REPOSITORY'] and
              event['ref']==env['GITHUB_REF'] and event['after']==after,'event/context consistency')
    b=dict(repository=env['GITHUB_REPOSITORY'],ref=env['GITHUB_REF'],event_name=env['GITHUB_EVENT_NAME'],
        private=event['repository']['private'],created=event['created'],deleted=event['deleted'],forced=event['forced'],
        before=event['before'],after=after,head_commit=event['head_commit']['id'],source_parent=source_parent,
        checkout_head=git('rev-parse','HEAD'),checkout_parent=git('show','-s','--format=%P','HEAD'),
        source_a_parent=git('show','-s','--format=%P',source),
        changed_at_b=git('diff-tree','--no-commit-id','--name-only','-r','HEAD').splitlines(),
        run_id=env['GITHUB_RUN_ID'],run_attempt=int(env['GITHUB_RUN_ATTEMPT']),
        workflow_ref=env['GITHUB_WORKFLOW_REF'],workflow_sha=env['GITHUB_WORKFLOW_SHA'],
        runner_environment=env['RUNNER_ENVIRONMENT'],runner_os=env['RUNNER_OS'],runner_arch=env['RUNNER_ARCH'],
        runner_label='ubuntu-24.04',image_os=env['ImageOS'],image_version=env['ImageVersion'],job_id=env['GITHUB_JOB'],
        job_container=None,container_steps=[],namespace_wrappers=[])
    policy.validate_provider(b,source_a=source,source_parent=source_parent)
    h.require(git('status','--porcelain','--untracked-files=all')=='','clean reviewed checkout')
    return b


def inspect_source(env,manifest_sha):
    activation_scope.require_actions_guard()
    root=runtime.HERE;workspace=Path(env['GITHUB_WORKSPACE']);deadline=h.Deadline(time.monotonic,60)
    h.require(workspace.is_absolute() and workspace.resolve()==workspace and root==workspace/policy.PROJECT,
              'source root must match checkout')
    def git(*args):
        # Read-only exact git invocations, one 60-second guard bound, no shell.
        result=subprocess.run(['/usr/bin/git',*args],cwd=workspace,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=min(10,deadline.remaining()),
            check=True,env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','PATH':'/usr/bin:/bin'})
        h.require(len(result.stdout)<=262144,'bounded source inventory output')
        return result.stdout.decode('utf-8','strict').strip()
    metadata=h.strict_json(activation_scope.read_guard_file(root/'INPUT_COMMITMENTS.json',16384))
    policy.validate_release_metadata(metadata)
    event=h.strict_json(activation_scope.read_guard_file(env['GITHUB_EVENT_PATH'],h.MIB))
    binding=provider_binding(event,env,git,source_parent=metadata['source_parent'])
    raw=activation_scope.read_guard_file(root/'KIT_MANIFEST.json',65536)
    h.require(h.digest(raw)==manifest_sha,'source manifest')
    manifest=h.strict_json(raw)
    files={item['path']:item for item in manifest['files']}
    for name,item in files.items():
        h.require(not Path(name).is_absolute() and '..' not in Path(name).parts,'relative inventory path')
        path=root/name;data=activation_scope.read_guard_file(path,2*h.MIB)
        h.require(path.resolve()==path and len(data)==item['bytes'] and h.digest(data)==item['sha256'],
                  'immutable source payload')
    expected={policy.PROJECT+'/'+name for name in files}|{policy.PROJECT+'/KIT_MANIFEST.json'}
    h.require(set(git('ls-tree','-r','--name-only','HEAD','--',policy.PROJECT).splitlines())==expected and
              set(git('diff-tree','--no-commit-id','--name-only','-r',binding['before']).splitlines())==expected,
              'A exact source-only tree')
    template=activation_scope.read_guard_file(root/'WORKFLOW_TEMPLATE.yml.in',32768).decode()
    for key,value in {'__REVIEWED_SOURCE_COMMIT_A__':binding['before'],
                      '__KIT_MANIFEST_SHA256__':manifest_sha,
                      '__BOOTSTRAP_SHA256__':files['verified_bootstrap.py']['sha256']}.items():
        template=template.replace(key,value)
    h.require(activation_scope.read_guard_file(workspace/policy.WORKFLOW,32768)==template.encode(),'exact sole B workflow')
    deadline.remaining();return binding,metadata


def assemble_plan(roots,binding,metadata,manifest_sha,python,*,coordinator_identity):
    """Pure path/receipt assembly. Missing preregistration hashes stop, never default."""
    policy.validate_release_metadata(metadata)
    paths=policy.validate_roots(roots);out=paths['output']
    commitments=deepcopy(metadata['commitments'])
    h.require(set(commitments)==set(h.CLAIM_EXTRA_HASHES)-{'harness_manifest','output_schemas','output_binding_revision'},
              'parent preregistration receipts required')
    output_policy=deepcopy(h.OUTPUT_POLICY);output_policy['fixed_root']=roots['state']
    commitments.update(harness_manifest=manifest_sha,output_schemas=h.digest(h.canonical(output_policy)),
                       output_binding_revision=h.OUTPUT_REVISION_SHA256)
    attempt=metadata['attempt_id'];empty={}
    result=dict(executor=policy.EXECUTOR,workspace=roots['workspace'],roots=roots,attempt_id=attempt,
        alias=h.alias_for(attempt),claimed_utc='1970-01-01T00:00:00Z',pins=deepcopy(h.PINS),
        assets=[list(a) for a in h.ASSETS],limits=deepcopy(h.LIMITS),sampling=deepcopy(h.SAMPLING),
        schedule_sha256=h.SCHEDULE_SHA256,commitments=commitments,
        paths=dict(acquisition=str(out/'staging'),extraction=str(out/'runtime'),output=str(out),evidence=str(out),
            source=roots['source'],claim_root=roots['state'],public=str(out/'public')),
        eligibility=sorted(h.ELIGIBLE_IDS),output_files=list(output_policy['output_files']),output_policy=output_policy,
        redirect_policy=deepcopy(acquisition.POLICY),execution_policy=policy.EXECUTION_POLICY,
        kit_contract_sha256=coordinator.KIT_CONTRACT_SHA256,component_manifest_sha256=manifest_sha,
        host_compatibility=deepcopy(host.HOST_POLICY),host_compatibility_sha256=h.digest(h.canonical(host.HOST_POLICY)),
        port=18080,absolute_python=python,worker_journal_reserved_bytes=65536,
        claimed_monotonic=0.,outer_deadline_monotonic=1475.,preclaim_host_evidence=empty,
        preclaim_host_evidence_sha256=h.digest(h.canonical(empty)),provider_binding=binding,
        source_a=binding['before'],source_parent=metadata['source_parent'],**coordinator_identity)
    coordinator.validate_kit_plan(result,manifest_sha);return result


def main(manifest_sha):
    try:activation_scope.require_actions_guard()
    except activation_scope.Denied as exc:raise h.Disabled(str(exc)) from None
    binding,metadata=inspect_source(os.environ,manifest_sha)
    workspace=Path(os.environ['GITHUB_WORKSPACE']);temp=Path(os.environ['RUNNER_TEMP'])
    h.require(temp.is_absolute() and temp.resolve()==temp and temp.is_dir(),'canonical runner temporary root')
    state=temp/policy.STATE_NAME
    roots=dict(workspace=str(workspace),source=str(runtime.HERE),runner_temp=str(temp),state=str(state),output=str(state/'attempt'))
    activation_scope.accept_actions(binding,metadata,roots,manifest_sha)
    plan=assemble_plan(roots,binding,metadata,manifest_sha,str(Path(sys.executable).resolve()),
                       coordinator_identity=activation_scope.owner_identity())
    runtime.bind_actions_roots(roots)
    # An explicitly non-final unknown snapshot preserves every planned row/call
    # even if host/claim/finalization fails before a final export can be produced.
    core,inventory,_=term_runtime_inventory.load(runtime)
    initial=public_exports.build_public(core,inventory,[],{},consumed_http=None,validated_http=None,
        accounting_confirmed=False,cleanup_confirmed=None,execution_kind='reviewed_native_evidence')
    for name,value in initial.items():
        line=b'LUNA_PUBLIC_JSON '+h.canonical(dict(snapshot='initial_unknown',file=name,data=value))+b'\n'
        sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
    # Exclusive directories are local collision guards. External one-shot identity
    # is reviewed A→B plus run_attempt=1, not persistent storage across runner VMs.
    os.mkdir(state,0o700);os.mkdir(state/'attempt',0o700)
    result=coordinator.main(base64.b64encode(h.canonical(plan)).decode(),manifest_sha)
    return public_exports.safe_terminal(result)
