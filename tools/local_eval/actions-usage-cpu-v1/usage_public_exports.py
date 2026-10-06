# Adapted only for the frozen 87-row usage experiment from the exact upstream
# public_exports.py recorded in UPSTREAM_PINS.json. Original closed privacy
# projection/finite diagnostics are retained; repository code license unchanged.
"""Closed public schema for authorized fictional sources/model translations.

No host dumps, exception text, headers, URLs, keys, criteria or opaque claim
objects are copied. Public treatment identities are intentional in this protocol.
Root prepares fresh anonymous reviewer packets later; blinding is not guaranteed.
"""
import math
import diagnostics
from usage_runner_core import ROW_IDS
import cpu_harness as h
from actions_policy import REVIEW_MODE


def finite(value):
    h.require(type(value) in (int,float) and math.isfinite(value) and value>=0,'public numeric field')
    return value


def build_public(core,inventory,sources,observations,*,consumed_http,validated_http,accounting_confirmed,
                 status,resource_metrics=None,protocol=None,diagnostic=None,helper_lifecycle=None,cleanup_confirmed=None,
                 helper_samples=None):
    h.require(type(sources) is dict and set(sources)==set(ROW_IDS) and
              all(type(text) is str and len(text)<=4096 for text in sources.values()),'public sources')
    h.require(type(observations) is dict and set(observations)<=set(inventory.schedule),'public observations')
    h.require(status in ('complete','incomplete','blocked_before_claim'),'public status')
    h.require(type(accounting_confirmed) is bool,'accounting certainty')
    h.require(cleanup_confirmed is None or type(cleanup_confirmed) is bool,'cleanup confirmation observation')
    if accounting_confirmed:
        h.require(type(consumed_http) is int and type(validated_http) is int and
                  0<=validated_http<=consumed_http<=inventory.request_total,'public call counters')
    else:
        h.require(consumed_http is None and validated_http is None,'unknown counters must stay unknown')
    source_rows=[dict(id=row,source=sources[row]) for row in ROW_IDS]
    translated=[];timings=[];generation_prompt_tokens=generated_tokens=0
    for row,arm in inventory.schedule:
        item=observations.get((row,arm))
        state='unobserved' if item is None else item.get('status')
        h.require(state in ('unobserved','operational_failure','observed'),'public observation state')
        public=dict(id=row,arm=arm,state=state,text=None,usage=None,generation_failure_flags=[])
        if state=='observed':
            text=item.get('output');usage=item.get('usage');flags=item.get('flags')
            h.require(type(text) is str and len(text.encode('utf-8'))<=65536,'public exact translation')
            h.require(type(usage) is dict and type(usage.get('prompt_tokens_details')) is dict,'public usage')
            p,c,t=(usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens'))
            cached=usage['prompt_tokens_details'].get('cached_tokens')
            h.require(all(type(v) is int for v in (p,c,t,cached)) and 1<=p<=384 and 0<=c<=512 and
                      cached==0 and t==p+c,'public usage integers/cache')
            h.require(type(flags) is list and len(flags)==len(set(flags)) and
                      set(flags)<= {'empty_output','length_finish','integrity_rejection'},'public generation flags')
            public.update(text=text,usage=dict(prompt_tokens=p,completion_tokens=c,total_tokens=t,cached_tokens=0),
                          generation_failure_flags=flags)
            generation_prompt_tokens+=p;generated_tokens+=c
            total=item.get('total_ns')
            h.require(type(total) is int and total>0,'public authoritative timing')
            timing=dict(id=row,arm=arm,total_ns=total,components=None)
            if item.get('components') is not None:
                parts=item['components'];counter=parts['token_counter_ns']
                h.require(type(counter) is list and len(counter)<=2 and all(type(v) is int and v>=0 for v in counter),
                          'public recurring token-counter elapsed times')
                selected={key:parts[key] for key in ('renderer_ns','construction_ns','completion_ns','integrity_ns')}
                h.require(all(type(v) is int and v>=0 for v in selected.values()),'public measured component nanoseconds')
                timing['components']=dict(token_counter_ns=counter,**selected)
            timings.append(timing)
        translated.append(public)
    h.require(generation_prompt_tokens<=66816 and generated_tokens<=89088,'public token accounting')
    calls=[]
    for index,(kind,row,arm) in enumerate(core.ledger(inventory).queue,1):
        state=('validated' if index<=validated_http else 'consumed_unvalidated' if index<=consumed_http else 'unissued') if accounting_confirmed else 'unknown'
        calls.append(dict(number=index,kind=kind,id=row,arm=arm,state=state))
    metrics=resource_metrics or {}
    allowed={'runner_peak_rss_bytes','server_peak_rss_bytes','helper_peak_rss_bytes','helper_render_p95_ns',
             'minimum_available_ram_bytes','minimum_effective_headroom_bytes'}
    h.require(type(metrics) is dict and set(metrics)<=allowed,'public resource allowlist')
    metrics={key:finite(value) for key,value in metrics.items()}
    lifecycle=None
    if helper_lifecycle is not None:
        fields={'active_work_ns','worker_cpu_ns','lifetime_ns','startup_ns','finish_ns','commands',
                'parent_setup_ns','parent_setup_cpu_ns'}
        h.require(type(helper_lifecycle) is dict and set(helper_lifecycle)==fields and
                  all(type(value) is int and value>=0 for value in helper_lifecycle.values()) and
                  helper_lifecycle['commands']<=224,'closed helper lifecycle projection')
        lifecycle={key:helper_lifecycle[key] for key in sorted(fields)}
    samples=sample_summary=None
    if helper_samples is not None:
        h.require(type(helper_samples) is list and len(helper_samples)<=87 and
                  all(type(item) is dict and set(item)=={'row','elapsed_ns'} and
                      type(item['elapsed_ns']) is int and item['elapsed_ns']>0 for item in helper_samples) and
                  [item['row'] for item in helper_samples]==list(ROW_IDS[:len(helper_samples)]),'closed ordered helper samples')
        samples=[dict(row=item['row'],elapsed_ns=item['elapsed_ns']) for item in helper_samples]
        sample_summary=dict(n=len(samples),complete=len(samples)==87,
            first_measured_candidate_ns=samples[0]['elapsed_ns'] if samples else None,
            first_measured_candidate_is_not_assumed_cold=True,
            quantiles=h.quantiles([item['elapsed_ns'] for item in samples]) if len(samples)==87 else None)
    reconciled=None
    if status=='complete':
        h.require(protocol is not None and cleanup_confirmed is True and lifecycle is not None and
                  lifecycle['commands']==224 and samples is not None and len(samples)==87,
                  'complete public result requires protocol, helper observations and cleanup')
    if protocol is not None:
        h.require(accounting_confirmed and consumed_http==validated_http==inventory.request_total and
                  len(observations)==174 and all(item['state']=='observed' for item in translated),
                  'reconciled public protocol must retain every completion and call')
        h.require(protocol.get('status')=='validated_complete_protocol_evidence','public reconciled protocol')
        cost=protocol['cost'];groups={}
        h.require(cost['status'] in ('pass','fail','inconclusive'),'public cost disposition')
        for name in ('fresh','active_fresh','all','all_active'):
            q=cost['groups'][name]['ratios']
            h.require(type(q['n']) is int and 1<=q['n']<=87,'public cost denominator')
            groups[name]=dict(n=q['n'],median=finite(q['median']),p95=finite(q['p95']))
        active=[dict(id=row['id'],active=row['active']) for row in cost['raw_rows']]
        h.require([r['id'] for r in active]==list(ROW_IDS) and all(type(r['active']) is bool for r in active),'public active membership')
        tokens={key:protocol['tokens'][key] for key in ('count_only_requests','count_only_input_tokens','generation_prompt_tokens','generated_tokens')}
        h.require(all(type(v) is int and v>=0 for v in tokens.values()),'public reconciled token totals')
        orders={}
        for order in ('AB','BA'):
            q=cost['order_strata'][order]['ratios']
            h.require(type(q['n']) is int and q['n']==(44 if order=='AB' else 43),'public order stratum denominator')
            orders[order]=dict(n=q['n'],median=finite(q['median']),p95=finite(q['p95']))
        reconciled=dict(status='validated_complete_protocol_evidence' ,cost_status=cost['status'],row_ratio_groups=groups,
                        active_membership=active,tokens=tokens,order_strata=orders)
    result={
        'sources.json':dict(schema=1,rows=source_rows),
        'translations.json':dict(schema=1,records=translated),
        'accounting.json':dict(schema=1,protocol_status=status,expected_rows=87,expected_completions=174,expected_http=inventory.request_total,
            consumed_http=consumed_http,validated_http=validated_http,accounting_confirmed=accounting_confirmed,
            cleanup_confirmed=cleanup_confirmed,protocol_evidence_complete=protocol is not None,
            observed_completions=sum(r['state']=='observed' for r in translated),calls=calls),
        'metrics.json':dict(schema=1,review_mode=REVIEW_MODE,semantic_quality_claim=None,
            generation_prompt_tokens=generation_prompt_tokens,generated_tokens=generated_tokens,
            raw_arm_timings=timings,resources=metrics,helper_lifecycle=lifecycle,
            helper_prepare_samples=samples,helper_sample_summary=sample_summary,reconciled_protocol=reconciled)}
    h.require(sum(len(h.canonical(value)) for value in result.values())<=16*h.MIB,'public export byte cap')
    result['diagnostic.json']=diagnostics.validate_public(diagnostic) if diagnostic is not None else diagnostics.Trace().snapshot()
    h.require(sum(len(h.canonical(value)) for value in result.values())<=16*h.MIB,'public export byte cap')
    result['manifest.json']=dict(schema=1,files=[dict(name=name,bytes=len(h.canonical(value)),
        sha256=h.digest(h.canonical(value))) for name,value in result.items()],private_data_included=False,
        treatment_identities_public=True,guaranteed_treatment_blinding=False)
    return result


def safe_terminal(result):
    """Print only selected booleans/enums, never raw causes or exception strings."""
    status=result.get('status') if type(result) is dict else None
    complete=type(result) is dict and status=='operationally_complete' and result.get('cleanup_confirmed') is True and result.get('protocol_complete') is True
    value=dict(schema=1,status='complete' if complete else 'incomplete',
        cleanup_confirmed=type(result) is dict and result.get('cleanup_confirmed') is True,
        protocol_complete=type(result) is dict and result.get('protocol_complete') is True,
        reason_code='COMPLETE' if complete else 'OPERATIONAL_FAILURE',
        review_mode=REVIEW_MODE)
    if type(result) is dict and result.get('diagnostic') is not None:
        value['diagnostic']=diagnostics.validate_public(result['diagnostic'])
    return value


def preflight_receipt(core, inventory, plans, manifest_sha, source_plan_sha):
    """Closed complete-preflight commitment before any translation completion."""
    import re
    h.require(tuple(plan.row_id for plan in plans) == ROW_IDS, "all87 preflight rows")
    h.require(all(type(value) is str and re.fullmatch("[0-9a-f]{64}", value)
                  for value in (manifest_sha, source_plan_sha)), "preflight receipt commitments")
    reasons = {"example_admitted", "token_budget", "no_match", "competing_full_anchors", "repeated_anchor",
               "selected_focus_outside_anchor", "protected_structure", "source_over_4096_chars", "baseline_out_of_scope"}
    rows = []
    for plan in plans:
        h.require(type(plan.eligible) is bool and type(plan.active) is bool and plan.reason in reasons and
                  (plan.record_id is None or plan.record_id in tuple(f"wb{i:02d}" for i in range(1,9))), "closed admission fields")
        counts = {}
        for name, receipt in (("baseline", plan.baseline), ("prospective", plan.provisional), ("actual_candidate", plan.candidate)):
            h.require(type(receipt.count) is int and receipt.count > 0 and type(receipt.body) is bytes and
                      len(receipt.body) <= 32768 and (name == "prospective" or receipt.count <= 384), "closed count/request receipt")
            h.require((receipt.runtime, receipt.model_tokenizer, receipt.template) ==
                      (h.PINS["server"],h.PINS["model"],h.PINS["template"]), "receipt asset binding")
            counts[name] = dict(input_tokens=receipt.count, request_sha256=h.digest(receipt.body))
        rows.append(dict(id=plan.row_id, eligible=plan.eligible, active=plan.active, reason=plan.reason,
                         record_id=plan.record_id, requests=counts))
    try:
        coverage = core.validate_preflight(inventory, plans)
        coverage_status = "pass"
    except h.TerminalFailure:
        coverage, coverage_status = None, "fail"
    result = dict(schema=1, component_manifest_sha256=manifest_sha, source_plan_sha256=source_plan_sha,
                  source_projection_sha256=inventory.source_digest, coverage_projection_sha256=inventory.metadata_digest,
                  schedule_projection_sha256=inventory.schedule_digest, execution_schedule_sha256=h.SCHEDULE_SHA256,
                  bank_sha256=inventory.bank_digest, planned_http=398, token_preflight_complete=True,
                  measured_completions_before_receipt=0, coverage_status=coverage_status, coverage=coverage, rows=rows)
    h.require(len(h.canonical(result)) <= 65536, "closed preflight receipt byte cap")
    return result
