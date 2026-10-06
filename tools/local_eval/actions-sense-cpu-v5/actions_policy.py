"""Narrow Actions trust/path policy. No API calls, credentials or attestation claims."""
from pathlib import Path
import re

REPOSITORY='yuxixi311/LunaTranslator-UI-Custom'
BRANCH='experiment/luna-actions-lexical-20261005'
WORKFLOW='.github/workflows/luna-sense-cpu-v5.yml'
PROJECT='tools/local_eval/actions-sense-cpu-v5'
STATE_NAME='luna-sense-cpu-20261005-v5'
EXECUTOR='github-actions-standard-ubuntu-24.04-x64'
EXECUTION_POLICY='verified-actions-and-owned-parent-v1'
SOURCE_A='__REVIEWED_SOURCE_COMMIT_A__'
SOURCE_PARENT='__REVIEWED_SOURCE_PARENT__'
RUNNER_LABEL='ubuntu-24.04'
PUBLIC_FILES=('public/sources.json','public/translations.json','public/accounting.json',
              'public/metrics.json','public/diagnostic.json','public/manifest.json')
REVIEW_MODE='public-arm-identified; subsequent-label-blind-review-without-guaranteed-treatment-blinding'


class PolicyError(ValueError):pass


def require(condition,code):
    if not condition:raise PolicyError(code)


def validate_provider(binding,*,source_a=SOURCE_A,source_parent=SOURCE_PARENT):
    """Trusted-service context plus immutable workflow policy; not a signature."""
    required={'repository','ref','event_name','private','created','deleted','forced','before','after',
        'head_commit','source_parent','checkout_head','checkout_parent','source_a_parent','changed_at_b',
        'run_id','run_attempt','workflow_ref','workflow_sha','runner_environment','runner_os','runner_arch',
        'runner_label','image_os','image_version','job_id','job_container','container_steps','namespace_wrappers'}
    require(type(binding) is dict and set(binding)==required,'PROVIDER_SCHEMA')
    require(re.fullmatch('[0-9a-f]{40}',source_a or '') and re.fullmatch('[0-9a-f]{40}',source_parent or ''),
            'SOURCE_BINDING_UNFROZEN')
    b=binding;after=b['after']
    require(type(after) is str and re.fullmatch('[0-9a-f]{40}',after) and after!=source_a,'TRIGGER_SHA')
    require(b['repository']==REPOSITORY and b['ref']=='refs/heads/'+BRANCH and b['event_name']=='push','EVENT_IDENTITY')
    require(all(b[key] is False for key in ('private','created','deleted','forced')),'EVENT_KIND')
    require(b['before']==source_a and b['checkout_parent']==source_a and
            b['source_parent']==source_parent and b['source_a_parent']==source_parent and
            b['head_commit']==after and b['checkout_head']==after and b['workflow_sha']==after and
            b['changed_at_b']==[WORKFLOW],'A_B_SOURCE_CHAIN')
    require(type(b['run_attempt']) is int and b['run_attempt']==1 and type(b['run_id']) is str and
            re.fullmatch('[1-9][0-9]{0,19}',b['run_id']),'ONE_SHOT_RUN')
    require(b['workflow_ref']==REPOSITORY+'/'+WORKFLOW+'@refs/heads/'+BRANCH and
            type(b['job_id']) is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',b['job_id']),'WORKFLOW_JOB')
    require((b['runner_environment'],b['runner_os'],b['runner_arch'],b['runner_label'],b['image_os'])==
            ('github-hosted','Linux','X64','ubuntu-24.04','ubuntu24'),'STANDARD_VM_PROVIDER')
    require(type(b['image_version']) is str and re.fullmatch('[A-Za-z0-9_.-]{1,80}',b['image_version']),
            'OBSERVED_IMAGE_VERSION')
    require(b['job_container'] is None and b['container_steps']==[] and b['namespace_wrappers']==[],
            'NON_CONTAINER_WORKFLOW')
    return True


def validate_roots(roots):
    require(type(roots) is dict and set(roots)=={'workspace','source','runner_temp','state','output'},'ROOT_SCHEMA')
    paths={key:Path(value) for key,value in roots.items()}
    require(all(type(roots[k]) is str and p.is_absolute() and str(p)==roots[k] and '..' not in p.parts
                for k,p in paths.items()),'CANONICAL_ABSOLUTE_ROOTS')
    require(paths['source']==paths['workspace']/PROJECT and
            paths['state']==paths['runner_temp']/STATE_NAME and paths['output']==paths['state']/'attempt',
            'BOUND_ROOT_DERIVATION')
    require(not paths['state'].is_relative_to(paths['workspace']) and not paths['workspace'].is_relative_to(paths['state']),
            'SOURCE_STATE_SEPARATION')
    return paths
